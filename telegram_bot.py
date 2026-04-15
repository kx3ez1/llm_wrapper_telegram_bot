import os
import requests
import logging
from typing import Optional, Dict, List, Tuple
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor
import tiktoken
from thread_store import SQLiteThreadStore

logger = logging.getLogger(__name__)

class TelegramBot:
    """
    TelegramBot provides methods to interact with the Telegram Bot API for text-only messaging and command handling.
    """
    def __init__(self, token: str, admin_id: int = None, bot_password: str = None):
        if not token or not token.strip():
            raise ValueError("Telegram bot token cannot be empty")
        self.token = token
        self.admin_id = admin_id
        self.bot_password = bot_password
        self.api_url = f"https://api.telegram.org/bot{self.token}/"
        db_path = os.getenv("THREAD_DB_PATH", "/app/data/threads.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.thread_store = SQLiteThreadStore(db_path)
        # In-memory cache of authenticated user_ids — loaded from DB on startup
        self.authenticated_users: set = self.thread_store.load_authenticated_user_ids()
        logger.info(f"Loaded {len(self.authenticated_users)} authenticated user(s) from DB")
        self._tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        # Optimize session for speed
        self.session = requests.Session()
        self.session.timeout = 10  # Reduced timeout for faster failures
        
        # Connection pooling for faster requests
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=1  # Quick retry
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # Keep-alive for persistent connections
        self.session.headers.update({'Connection': 'keep-alive'})
        
        logger.info("TelegramBot initialized with speed optimizations")

    def send_message(self, chat_id: int, text: str, reply_to_message_id: int = None, parse_mode: str = None) -> dict:
        """
        Send a message to a chat. Automatically splits messages longer than 4096 characters.
        :param chat_id: Telegram chat ID
        :param text: Message text
        :param reply_to_message_id: (Optional) ID of the message to reply to
        :param parse_mode: (Optional) 'Markdown', 'MarkdownV2', or 'HTML' for formatting
        """
        if not text or not text.strip():
            logger.warning("Attempted to send empty message")
            return {"ok": False, "error": "Message text cannot be empty"}
        
        # Split long messages into chunks
        max_length = 4076
        if len(text) <= max_length:
            return self._send_single_message(chat_id, text, reply_to_message_id, parse_mode)
        
        # Split message into chunks
        chunks = []
        for i in range(0, len(text), max_length):
            chunk = text[i:i + max_length]
            chunks.append(chunk)
        
        logger.info(f"Splitting message into {len(chunks)} chunks")
        
        # Send chunks sequentially
        results = []
        for i, chunk in enumerate(chunks):
            # Add chunk indicator for multiple parts
            if len(chunks) > 1:
                chunk_text = f"[Part {i+1}/{len(chunks)}]\n\n{chunk}"
            else:
                chunk_text = chunk
            
            # Only use reply_to_message_id for the first chunk
            reply_id = reply_to_message_id if i == 0 else None
            result = self._send_single_message(chat_id, chunk_text, reply_id, parse_mode)
            results.append(result)
            
            # Small delay between chunks to avoid rate limiting
            if i < len(chunks) - 1:
                time.sleep(0.5) # 500 milliseconds
        
        # Return result of last chunk (or combined status)
        return {
            "ok": all(r.get("ok", False) for r in results),
            "results": results,
            "chunks_sent": len(results)
        }

    def _send_single_message(self, chat_id: int, text: str, reply_to_message_id: int = None, parse_mode: str = None) -> dict:
        """
        Send a single message without splitting.
        """
        url = self.api_url + "sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        try:
            response = self.session.post(url, data=payload)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                logger.error(f"Telegram API error: {result.get('description')}")
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to send message: {e}")
            return {"ok": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            return {"ok": False, "error": "Unexpected error occurred"}

    def send_processing_message(self, chat_id: int, reply_to_message_id: int = None) -> dict:
        """
        Send a user-friendly processing message.
        """
        processing_messages = [
            "🤖 Processing your request...",
            "⏳ Thinking...",
            "🧠 Processing...",
            "⚡ Working on it..."
        ]
        message = random.choice(processing_messages)
        return self.send_message(chat_id, message, reply_to_message_id)

    def get_updates(self, offset: int = None) -> dict:
        """
        Retrieve updates from the Telegram API.
        """
        url = self.api_url + "getUpdates"
        params = {"timeout": 2}  # Shorter timeout for faster responses
        if offset:
            params['offset'] = offset
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                logger.error(f"Failed to get updates: {result.get('description')}")
                return {"ok": False, "result": []}
            return result
        except requests.RequestException as e:
            logger.error(f"Failed to get updates: {e}")
            return {"ok": False, "result": []}
        except Exception as e:
            logger.error(f"Unexpected error getting updates: {e}")
            return {"ok": False, "result": []}

    def get_user_messages(self, user_id: int, offset: int = None) -> list:
        """
        Get all messages from a specific user.
        """
        updates = self.get_updates(offset)
        user_messages = []
        for update in updates.get('result', []):
            if 'message' in update and update['message']['from']['id'] == user_id:
                user_messages.append(update['message'])
        return user_messages

    def get_commands(self, offset: int = None) -> list:
        """
        Returns a list of command messages with their details.
        """
        updates = self.get_updates(offset)
        commands = []
        for update in updates.get('result', []):
            message = update.get('message', {})
            text = message.get('text', '')
            if text and text.startswith('/'):
                parts = text.split(maxsplit=1)
                command = parts[0][1:]
                args = parts[1] if len(parts) > 1 else ''
                commands.append({
                    'chat_id': message.get('chat', {}).get('id'),
                    'message_id': message.get('message_id'),
                    'command': command,
                    'args': args,
                    'from_id': message.get('from', {}).get('id')
                })
        return commands

    def parse_command(self, text: str) -> Optional[Dict[str, str]]:
        """
        Parse a command message and extract command name and arguments.
        Returns None if not a command.
        """
        if not text or not text.startswith('/'):
            return None
        
        parts = text.split(maxsplit=1)
        command = parts[0][1:].lower()  # Remove '/' and convert to lowercase
        args = parts[1] if len(parts) > 1 else ''
        
        return {
            'command': command,
            'args': args,
            'raw_text': text
        }
    
    def handle_command(self, chat_id: int, user_info: Dict, command_data: Dict) -> bool:
        """
        Handle a parsed command. Returns True if command was handled, False otherwise.
        """
        command = command_data['command']
        args = command_data['args']
        username = user_info.get('username', 'Unknown')
        
        logger.info(f"Handling command '{command}' from user {username}")
        
        # Command handlers
        if command in ['start', 'help']:
            return self._handle_help_command(chat_id)
        elif command == 'about':
            return self._handle_about_command(chat_id)
        elif command == 'ping':
            return self._handle_ping_command(chat_id)
        elif command == 'status':
            return self._handle_status_command(chat_id, user_info)
        elif command == 'clear':
            return self._handle_clear_command(chat_id)
        elif command == 'newtoken':
            return self._handle_newtoken_command(chat_id, user_info)
        elif command == 'revoke':
            return self._handle_revoke_command(chat_id, user_info, args)
        elif command == 'tokens':
            return self._handle_tokens_command(chat_id, user_info)
        else:
            return self._handle_unknown_command(chat_id, command)
    
    def _handle_help_command(self, chat_id: int) -> bool:
        """
        Handle /start and /help commands.
        """
        help_text = (
            "🤖 *Available Commands:*\n\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/about - About this bot\n"
            "/ping - Check if bot is responsive\n"
            "/status - Show your user status\n"
            "/clear - Clear chat (info only)\n\n"
            "💬 *How to use:*\n"
            "Just send me any message and I'll respond with AI assistance!"
        )
        result = self.send_message(chat_id, help_text, parse_mode="Markdown")
        return result.get('ok', False)
    
    def _handle_about_command(self, chat_id: int) -> bool:
        """
        Handle /about command.
        """
        about_text = (
            "🤖 *Telegram AI Bot*\n\n"
            "This bot is powered by Azure AI and provides intelligent responses to your messages.\n\n"
            "✨ *Features:*\n"
            "• Natural language processing\n"
            "• Markdown formatting support\n"
            "• Command handling\n"
            "• Error handling & logging\n\n"
            "📝 Just send me any question or message!"
        )
        result = self.send_message(chat_id, about_text, parse_mode="Markdown")
        return result.get('ok', False)
    
    def _handle_ping_command(self, chat_id: int) -> bool:
        """
        Handle /ping command.
        """
        result = self.send_message(chat_id, "🏓 Pong! Bot is running smoothly.")
        return result.get('ok', False)
    
    def _handle_status_command(self, chat_id: int, user_info: Dict) -> bool:
        """
        Handle /status command.
        """
        username = user_info.get('username', 'Not set')
        user_id = user_info.get('id', 'Unknown')
        first_name = user_info.get('first_name', 'Unknown')
        
        status_text = (
            f"👤 *Your Status:*\n\n"
            f"**Name:** {first_name}\n"
            f"**Username:** @{username}\n"
            f"**User ID:** `{user_id}`\n"
            f"**Chat ID:** `{chat_id}`\n\n"
            f"✅ Connected and ready to chat!"
        )
        result = self.send_message(chat_id, status_text, parse_mode="Markdown")
        return result.get('ok', False)
    
    def _handle_clear_command(self, chat_id: int) -> bool:
        """
        Handle /clear command - explain limitations.
        """
        clear_text = (
            "🧹 *Clear Chat*\n\n"
            "ℹ️ **Note:** Telegram bots cannot delete user messages or clear chat history for privacy reasons.\n\n"
            "**To clear your chat:**\n"
            "1️⃣ Tap the chat settings (three dots)\n"
            "2️⃣ Select 'Clear History'\n"
            "3️⃣ Confirm the action\n\n"
            "The bot can only delete its own messages in group chats where it has admin permissions."
        )
        result = self.send_message(chat_id, clear_text, parse_mode="Markdown")
        return result.get('ok', False)
    
    def _handle_newtoken_command(self, chat_id: int, user_info: Dict) -> bool:
        if not self.is_admin(user_info.get('id')):
            result = self.send_message(chat_id, "⛔ Admin only.")
            return result.get('ok', False)
        token = self.thread_store.create_token(created_by=user_info['id'])
        result = self.send_message(
            chat_id,
            f"🔑 *New token created:*\n\n`{token}`\n\nShare this with the user. It works immediately.",
            parse_mode="Markdown",
        )
        return result.get('ok', False)

    def _handle_revoke_command(self, chat_id: int, user_info: Dict, args: str) -> bool:
        if not self.is_admin(user_info.get('id')):
            result = self.send_message(chat_id, "⛔ Admin only.")
            return result.get('ok', False)
        token = args.strip().upper()
        if not token:
            result = self.send_message(chat_id, "Usage: `/revoke TOKEN`", parse_mode="Markdown")
            return result.get('ok', False)
        # Find who owns this token before revoking so we can evict from cache
        owner_id = self.thread_store.get_user_id_for_token(token)
        ok = self.thread_store.revoke_token(token)
        if ok:
            if owner_id and owner_id in self.authenticated_users:
                # Re-check DB — user may have other active tokens
                if not self.thread_store.is_user_authenticated(owner_id):
                    self.authenticated_users.discard(owner_id)
                    logger.info(f"User {owner_id} evicted from session after token {token} revoked")
            result = self.send_message(chat_id, f"✅ Token `{token}` revoked.", parse_mode="Markdown")
        else:
            result = self.send_message(chat_id, f"❌ Token `{token}` not found.", parse_mode="Markdown")
        return result.get('ok', False)

    def _handle_tokens_command(self, chat_id: int, user_info: Dict) -> bool:
        if not self.is_admin(user_info.get('id')):
            result = self.send_message(chat_id, "⛔ Admin only.")
            return result.get('ok', False)
        tokens = self.thread_store.list_tokens()
        if not tokens:
            result = self.send_message(chat_id, "No tokens yet. Use /newtoken to create one.")
            return result.get('ok', False)
        lines = ["*Tokens:*\n"]
        for t in tokens:
            if not t['is_active']:
                icon = "❌"
                note = "revoked"
            elif t['used_by']:
                icon = "✅"
                note = f"used by `{t['used_by']}`"
            else:
                icon = "⏳"
                note = "unused"
            lines.append(f"{icon} `{t['token']}` — {note}")
        result = self.send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
        return result.get('ok', False)

    def _handle_unknown_command(self, chat_id: int, command: str) -> bool:
        """
        Handle unknown commands.
        """
        unknown_text = (
            f"❓ Unknown command: `/{command}`\n\n"
            "Use /help to see available commands."
        )
        result = self.send_message(chat_id, unknown_text, parse_mode="Markdown")
        return result.get('ok', False)
    
    def get_message_by_id(self, chat_id: int, message_id: int) -> Optional[Dict]:
        """
        Get a specific message by its ID from recent updates.
        Note: This is limited to recent messages in the updates buffer.
        """
        try:
            updates = self.get_updates()
            for update in updates.get('result', []):
                message = update.get('message', {})
                if (message.get('chat', {}).get('id') == chat_id and 
                    message.get('message_id') == message_id):
                    return message
        except Exception as e:
            logger.error(f"Error getting message by ID: {e}")
        return None
    
    def format_reply_context(self, original_message: Dict, reply_message: Dict) -> str:
        """
        Format the original message and reply into context for AI processing.
        """
        original_text = original_message.get('text', '[No text]')
        original_user = original_message.get('from', {}).get('first_name', 'Unknown')
        
        reply_text = reply_message.get('text', '[No text]')
        reply_user = reply_message.get('from', {}).get('first_name', 'Unknown')
        
        context = f"""Previous message from {original_user}:
"{original_text}"

Reply from {reply_user}:
"{reply_text}"

Please respond to this conversation considering both messages for context."""
        
        return context
    
    def is_authenticated(self, user_id: int) -> bool:
        return user_id in self.authenticated_users or user_id == self.admin_id

    def is_admin(self, user_id: int) -> bool:
        return self.admin_id is not None and user_id == self.admin_id

    def handle_authentication(self, chat_id: int, user_id: int, text: str) -> bool:
        """
        Token-based auth flow. Returns True if the message was consumed by auth.
        Admin is always authenticated — no token needed.
        """
        # Admin bypasses everything
        if self.is_admin(user_id):
            return False

        cmd = text.strip().lower()

        if cmd == "/start":
            if self.is_authenticated(user_id):
                self.send_message(chat_id, "✅ You're already authenticated. Type /help to see commands.")
            else:
                self.send_message(
                    chat_id,
                    "🔐 *Access token required*\n\nSend your access token to continue.",
                    parse_mode="Markdown",
                )
            return True

        if not self.is_authenticated(user_id):
            candidate = text.strip()
            # Global password check (admin-only knowledge, no DB entry needed)
            if self.bot_password and candidate == self.bot_password:
                self.authenticated_users.add(user_id)
                self.send_message(
                    chat_id,
                    "✅ *Access granted!*\n\nType /help to see available commands.",
                    parse_mode="Markdown",
                )
                return True
            # Per-user token check
            ok = self.thread_store.claim_token(candidate.upper(), user_id)
            if ok:
                self.authenticated_users.add(user_id)
                self.send_message(
                    chat_id,
                    "✅ *Access granted!*\n\nType /help to see available commands.",
                    parse_mode="Markdown",
                )
            else:
                self.send_message(
                    chat_id,
                    "🔒 *Invalid or revoked token.*\n\nContact the admin for an access token.",
                    parse_mode="Markdown",
                )
            return True

        return False
    
    def store_thread_message(self, user_id: int, message_id: int, chat_id: int, role: str, content: str, parent_id: int = None) -> None:
        """
        Persist a message to the SQLite thread store.
        Only called when /thread is used.
        """
        self.thread_store.store(user_id, message_id, chat_id, role, content, parent_id)

    def _count_tokens(self, text: str) -> int:
        return len(self._tiktoken_enc.encode(text))

    def parse_thread_range(self, args: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """
        Parse /thread range args like Python slice: [start]:[stop]:[step]
        Returns (start, stop, step) — any can be None meaning use default.
        Single int is treated as stop (e.g. /thread 3 → go back 3 levels).
        """
        args = args.strip()
        if not args:
            return None, None, None
        parts = args.split(":")
        def _int(s):
            s = s.strip()
            return int(s) if s else None
        try:
            if len(parts) == 1:
                val = _int(parts[0])
                return 1, val, None  # start=1, stop=val, step=None
            elif len(parts) == 2:
                return _int(parts[0]) or 1, _int(parts[1]), None
            elif len(parts) == 3:
                return _int(parts[0]) or 1, _int(parts[1]), _int(parts[2])
            else:
                return None, None, None  # invalid
        except ValueError:
            return None, None, None  # parse error

    def build_thread_context(
        self,
        user_id: int,
        root_message_id: int,
        start: Optional[int],
        stop: Optional[int],
        step: Optional[int],
        max_tokens: int = 120000,
        system_prompt_tokens: int = 200,
        response_reserve: int = 2000,
    ) -> Tuple[List[Dict], int]:
        """
        Walk the thread chain from root_message_id upward for a specific user.
        Returns (messages_list, count_included).

        Chain is collected as depths: depth 1 = direct parent, depth 2 = grandparent, etc.
        Range [start:stop:step] selects which depths to include (1-based, like Python range).
        Default (all None): include all depths within token budget.
        Token budget = max_tokens - system_prompt_tokens - response_reserve.
        """
        budget = max_tokens - system_prompt_tokens - response_reserve

        # Walk full chain upward, collect (depth, message)
        chain = []
        current_id = root_message_id
        depth = 0
        while current_id is not None:
            entry = self.thread_store.get(user_id, current_id)
            if not entry:
                break
            depth += 1
            chain.append((depth, entry))
            current_id = entry.get("parent_id")

        if not chain:
            return [], 0

        max_depth = chain[-1][0]

        def _resolve(val):
            """Convert negative index to positive depth (Python-style, from oldest end)."""
            if val is None or val >= 0:
                return val
            resolved = max_depth + val + 1
            return max(1, resolved)

        # Build depth indices to include based on range
        if start is None and stop is None and step is None:
            depths_to_include = list(range(1, max_depth + 1))
        else:
            _start = _resolve(start) or 1
            _stop = _resolve(stop) if stop is not None else max_depth
            _step = step or 1
            depths_to_include = list(range(_start, _stop + 1, _step))

        # Filter chain to only selected depths
        selected = [(d, e) for d, e in chain if d in depths_to_include]

        # Apply token budget — fill from most recent (lowest depth) until budget exhausted
        included = []
        used_tokens = 0
        for depth_val, entry in selected:  # already ordered nearest-first
            tokens = self._count_tokens(entry["content"])
            if used_tokens + tokens > budget:
                break
            included.append((depth_val, entry))
            used_tokens += tokens

        # Reverse to chronological order (oldest first) for OpenAI messages array
        included.reverse()
        messages = [{"role": e["role"], "content": e["content"]} for _, e in included]
        return messages, len(messages)

    def show_commands(self, chat_id: int):
        """
        Deprecated: Use handle_command with 'help' instead.
        """
        self._handle_help_command(chat_id)