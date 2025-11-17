import requests
import logging
from typing import Optional, Dict, List
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramBot:
    """
    TelegramBot provides methods to interact with the Telegram Bot API for text-only messaging and command handling.
    """
    def __init__(self, token: str):
        if not token or not token.strip():
            raise ValueError("Telegram bot token cannot be empty")
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{self.token}/"
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
        Send a message to a chat. Optionally supports Markdown or HTML formatting via parse_mode.
        :param chat_id: Telegram chat ID
        :param text: Message text
        :param reply_to_message_id: (Optional) ID of the message to reply to
        :param parse_mode: (Optional) 'Markdown', 'MarkdownV2', or 'HTML' for formatting
        """
        if not text or not text.strip():
            logger.warning("Attempted to send empty message")
            return {"ok": False, "error": "Message text cannot be empty"}
        
        # Truncate message if too long (Telegram limit is 4096 characters)
        if len(text) > 4096:
            text = text[:4093] + "..."
            logger.warning(f"Message truncated to fit Telegram limit")
        
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

    def get_updates(self, offset: int = None) -> dict:
        """
        Retrieve updates from the Telegram API.
        """
        url = self.api_url + "getUpdates"
        params = {"timeout": 2}  # Shorter timeout for faster responses
        if offset:
            params['offset'] = offset
        
        try:
            response = self.session.get(url, params=params)
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
    
    def show_commands(self, chat_id: int):
        """
        Deprecated: Use handle_command with 'help' instead.
        """
        self._handle_help_command(chat_id)