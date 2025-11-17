import time
import requests
import logging
from dotenv import load_dotenv
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import asyncio

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
if not telegram_bot_token:
    logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
    exit(1)

from telegram_bot import TelegramBot
from services import get_azure_ai_response_model_router2

try:
    bot = TelegramBot(telegram_bot_token)
except ValueError as e:
    logger.error(f"Failed to initialize bot: {e}")
    exit(1)

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
                context = bot.format_reply_context(reply_to_message, message)
                response = get_azure_ai_response_model_router2(context)
                result = bot.send_message(chat_id, response, reply_to_message_id=message.get('message_id'))
                if result.get('ok'):
                    logger.info(f"Successfully sent AI reply response to {username}")
                else:
                    logger.error(f"Failed to send reply response to {username}: {result.get('error')}")
            else:
                # Treat as regular user prompt, process and show response
                logger.info(f"Processing AI request for user {username}")
                response = get_azure_ai_response_model_router2(text)
                result = bot.send_message(chat_id, response)
                if result.get('ok'):
                    logger.info(f"Successfully sent AI response to {username}")
                else:
                    logger.error(f"Failed to send response to {username}: {result.get('error')}")
                    
    except Exception as e:
        logger.error(f"Error processing message from {username}: {e}")
        try:
            bot.send_message(chat_id, "Sorry, I encountered an error processing your request. Please try again.")
        except:
            pass

logger.info("Bot started successfully with concurrent processing. Listening for messages...")

while True:
    try:
        updates = bot.get_updates(offset=last_update_id)
        
        if not updates.get('ok'):
            logger.warning("Failed to get updates, retrying...")
            time.sleep(5)
            continue
            
        retry_count = 0  # Reset retry count on successful update
        
        for update in updates.get('result', []):
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