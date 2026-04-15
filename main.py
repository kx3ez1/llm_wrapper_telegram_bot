
# Standard library imports
import os
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

# Get bot password from environment (optional)
bot_password = os.getenv("BOT_PASSWORD")
if bot_password:
    logger.info("Bot password protection enabled")
else:
    logger.warning("No bot password set - bot will be publicly accessible")



try:
    bot = TelegramBot(telegram_bot_token, bot_password)
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
    {"command": "clear", "description": "Clear chat instructions"}
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
        
        # Parse and handle commands
        command_data = bot.parse_command(text)
        if command_data:
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
            # Check if this is a reply to another message
            reply_to_message = message.get('reply_to_message')
            
            if reply_to_message:
                # Handle reply message - combine with original for context
                logger.info(f"Processing reply message from {username}")
                # Send processing message
                bot.send_processing_message(chat_id, message.get('message_id'))
                context = bot.format_reply_context(reply_to_message, message)
                response = get_openai_response(context)
                result = bot.send_message(chat_id, response, reply_to_message_id=message.get('message_id'))
                if result.get('ok'):
                    logger.info(f"Successfully sent AI reply response to {username}")
                else:
                    logger.error(f"Failed to send reply response to {username}: {result.get('error')}")
            else:
                # Treat as regular user prompt, process and show response
                logger.info(f"Processing AI request for user {username}")
                # Send processing message
                bot.send_processing_message(chat_id, message.get('message_id'))
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