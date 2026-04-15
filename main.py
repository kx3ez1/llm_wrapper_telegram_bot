
# Standard library imports
import os
import re
import time
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
 
# Third-party imports
import requests
from dotenv import load_dotenv


# Local imports
from telegram_bot import TelegramBot
from services import get_openai_response


load_dotenv()

# Create logs directory if it doesn't exist
log_dir = '/app/logs'
os.makedirs(log_dir, exist_ok=True)

# Configure logging — single source of truth; child loggers propagate here
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

_file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'bot.log'),
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3
)
_file_handler.setFormatter(_formatter)
_file_handler.setLevel(_log_level)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
_console_handler.setLevel(_log_level)

logging.root.setLevel(_log_level)
logging.root.addHandler(_file_handler)
logging.root.addHandler(_console_handler)

logger = logging.getLogger(__name__)

telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
if not telegram_bot_token:
    logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
    exit(1)

admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID")
if admin_id_raw:
    try:
        admin_id = int(admin_id_raw)
        logger.info(f"Admin user set: {admin_id}")
    except ValueError:
        logger.error("ADMIN_TELEGRAM_ID must be an integer")
        exit(1)
else:
    admin_id = None
    logger.warning("No ADMIN_TELEGRAM_ID set — token management commands will be unavailable")

bot_password = os.getenv("BOT_PASSWORD")
if bot_password:
    logger.info("Global BOT_PASSWORD set")

try:
    bot = TelegramBot(telegram_bot_token, admin_id, bot_password)
except ValueError as e:
    logger.error(f"Failed to initialize bot: {e}")
    exit(1)

# Delete any active webhook to avoid 409 conflicts with long-polling
try:
    delete_webhook_url = f"https://api.telegram.org/bot{telegram_bot_token}/deleteWebhook"
    wh_response = requests.post(delete_webhook_url, json={"drop_pending_updates": False})
    if wh_response.status_code == 200 and wh_response.json().get("result"):
        logger.info("Webhook cleared — long-polling is safe to start")
    else:
        logger.warning(f"deleteWebhook returned unexpected result: {wh_response.text}")
except Exception as e:
    logger.error(f"Error clearing webhook: {e}")

# Set Telegram bot command menu for better UI experience
command_menu = [
    {"command": "start", "description": "Start the bot"},
    {"command": "help", "description": "Show help message"},
    {"command": "about", "description": "About this bot"},
    {"command": "ping", "description": "Check bot status"},
    {"command": "status", "description": "Show your user info"},
    {"command": "clear", "description": "Clear chat instructions"},
    {"command": "newtoken", "description": "(Admin) Generate a new access token"},
    {"command": "revoke", "description": "(Admin) Revoke a token"},
    {"command": "tokens", "description": "(Admin) List all tokens"},
]
set_commands_url = f"https://api.telegram.org/bot{telegram_bot_token}/setMyCommands"
try:
    response = requests.post(set_commands_url, json={"commands": command_menu})
    if response.status_code == 200:
        logger.info("Bot commands menu set successfully")
    else:
        logger.warning(f"Failed to set commands menu: {response.status_code}")
except Exception as e:
    logger.error(f"Error setting commands menu: {e}")

last_update_id = None
max_retries = 3
retry_count = 0

# Thread pool for concurrent message processing
executor = ThreadPoolExecutor(max_workers=5)

def process_message_async(bot, message, chat_id, text, user_id, username):
    """
    Process a single message asynchronously for faster responses.
    """
    try:
        logger.info(f"Processing message from {username} ({user_id}): {text[:50]}{'...' if len(text) > 50 else ''}")
        
        # Check authentication first
        if bot.handle_authentication(chat_id, user_id, text):
            # Message was handled by authentication system
            return
        
        # /thread must be checked before generic command parsing
        if text.startswith('/thread'):
            reply_to_message = message.get('reply_to_message')
            message_id = message.get('message_id')

            parts = text.split(maxsplit=1)
            raw_args = parts[1] if len(parts) > 1 else ''
            m = re.match(r'^([-\d\s:]*)(.*)', raw_args.strip(), re.DOTALL)
            range_str = m.group(1).replace(' ', '').strip(':') if m else ''
            thread_prompt = m.group(2).strip() if m else raw_args.strip()

            if not reply_to_message:
                bot.send_message(chat_id, "⚠️ `/thread` must be used as a reply to a message.", parse_mode="Markdown")
                return
            if not thread_prompt.strip():
                bot.send_message(chat_id, "⚠️ `/thread` requires a prompt. Example: `/thread 1:5:2 explain this`", parse_mode="Markdown")
                return

            parent_id = reply_to_message.get('message_id')
            if not parent_id:
                bot.send_message(chat_id, "⚠️ Could not read the replied-to message ID.", parse_mode="Markdown")
                return

            range_desc = range_str if range_str else "default (all)"

            try:
                start, stop, step = bot.parse_thread_range(range_str)
                thread_messages, count = bot.build_thread_context(
                    user_id=user_id,
                    root_message_id=parent_id,
                    start=start,
                    stop=stop,
                    step=step,
                )
            except Exception as e:
                logger.error(f"Thread context build failed for {username}: {e}")
                bot.send_message(chat_id, f"⚠️ *Thread:* failed to build context — `{e}`", parse_mode="Markdown")
                return

            if count == 0:
                bot.send_message(
                    chat_id,
                    f"🧵 *Thread:* range `{range_desc}` → no history found, starting fresh",
                    parse_mode="Markdown"
                )
                thread_messages = None
            else:
                bot.send_message(
                    chat_id,
                    f"🧵 *Thread:* range `{range_desc}` → {count} message{'s' if count != 1 else ''} loaded",
                    parse_mode="Markdown"
                )

            logger.info(f"Thread context: range={range_desc}, count={count} for {username}")
            bot.send_processing_message(chat_id, message_id)

            try:
                response = get_openai_response(thread_prompt, messages=thread_messages)
            except Exception as e:
                logger.error(f"OpenAI call failed for thread from {username}: {e}")
                bot.send_message(chat_id, "⚠️ Failed to get AI response. Please try again.")
                return

            result = bot.send_message(chat_id, response, reply_to_message_id=message_id)
            if result.get('ok'):
                bot.store_thread_message(user_id, message_id, chat_id, "user", thread_prompt, parent_id=parent_id)
                bot_message_id = result.get('result', {}).get('message_id')
                if bot_message_id:
                    bot.store_thread_message(user_id, bot_message_id, chat_id, "assistant", response, parent_id=message_id)
                logger.info(f"Thread response sent to {username}")
            else:
                logger.error(f"Failed to send thread response to {username}: {result.get('error')}")

        # Parse and handle other commands
        elif bot.parse_command(text):
            command_data = bot.parse_command(text)
            user_info = {
                'id': user_id,
                'username': username,
                'first_name': message.get('from', {}).get('first_name', 'Unknown')
            }
            success = bot.handle_command(chat_id, user_info, command_data)
            if success:
                logger.info(f"Successfully handled command '{command_data['command']}' for {username}")
            else:
                logger.warning(f"Failed to handle command '{command_data['command']}' for {username}")

        else:
            reply_to_message = message.get('reply_to_message')
            message_id = message.get('message_id')

            if reply_to_message:
                # Regular reply — single-level context (existing behaviour)
                logger.info(f"Processing reply message from {username}")
                bot.send_processing_message(chat_id, message_id)
                context = bot.format_reply_context(reply_to_message, message)
                response = get_openai_response(context)
                result = bot.send_message(chat_id, response, reply_to_message_id=message_id)
                if result.get('ok'):
                    logger.info(f"Successfully sent AI reply response to {username}")
                else:
                    logger.error(f"Failed to send reply response to {username}: {result.get('error')}")
            else:
                # Standalone message
                logger.info(f"Processing AI request for user {username}")
                bot.send_processing_message(chat_id, message_id)
                response = get_openai_response(text)
                result = bot.send_message(chat_id, response)
                if result.get('ok'):
                    logger.info(f"Successfully sent AI response to {username}")
                else:
                    logger.error(f"Failed to send response to {username}: {result.get('error')}")
                    
    except Exception as e:
        logger.error(f"Error processing message from {username}: {e}")
        try:
            bot.send_message(chat_id, "Sorry, I encountered an error processing your request. Please try again.")
        except Exception as send_err:
            logger.error(f"Failed to send error message to {username}: {send_err}")

logger.info("Bot started successfully with concurrent processing. Listening for messages...")

while True:
    try:
        updates = bot.get_updates(offset=last_update_id)
        
        if not updates.get('ok'):
            logger.warning("Failed to get updates, retrying...")
            time.sleep(5)
            continue
            
        retry_count = 0  # Reset retry count on successful update

        results = updates.get('result', [])
        if results:
            logger.debug(f"Got {len(results)} update(s) from Telegram")

        for update in results:
            try:
                message = update.get('message', {})
                chat_id = message.get('chat', {}).get('id')
                text = message.get('text', '')
                user_id = message.get('from', {}).get('id')
                username = message.get('from', {}).get('username', 'Unknown')
                
                if not text or not chat_id:
                    last_update_id = update['update_id'] + 1
                    continue
                
                logger.info(f"Received message from {username} ({user_id})")
                
                # Process message concurrently for faster response
                executor.submit(process_message_async, bot, message, chat_id, text, user_id, username)
                        
                last_update_id = update['update_id'] + 1
                
            except Exception as e:
                logger.error(f"Error processing update: {e}")
                continue
                
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        executor.shutdown(wait=True)
        break
    except Exception as e:
        retry_count += 1
        logger.error(f"Unexpected error in main loop (attempt {retry_count}/{max_retries}): {e}")
        
        if retry_count >= max_retries:
            logger.critical("Max retries reached. Exiting.")
            break
            
        time.sleep(10)  # Wait before retrying
        continue
        
    # Minimal sleep
    time.sleep(0.5)