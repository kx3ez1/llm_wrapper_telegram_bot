# LLM Wrapper Telegram Bot

A fast, production-ready Telegram bot that leverages Azure AI for intelligent, markdown-formatted responses. Includes Docker support, health checks, and robust command handling.

## Features

- **Telegram Bot API** integration
- **Azure AI** (OpenAI-compatible) backend
- Markdown formatting in responses
- Command handling: `/start`, `/help`, `/about`, `/ping`, `/status`, `/clear`
- Error handling and logging
- Docker & Docker Compose support
- Health checks and resource limits
- Concurrent message processing for speed

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- Telegram Bot Token ([@BotFather](https://t.me/botfather))
- Azure AI API Key

### 2. Setup Environment

Copy the example environment file and edit with your credentials:
```sh
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN and AZURE_API_KEY
```

Or create `.env` manually:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
AZURE_API_KEY=your_azure_api_key
ENVIRONMENT=development
```

### 3. Run Locally

Install dependencies:
```sh
pip install -r requirements.txt
```

Start the bot:
```sh
python main.py
```

### 4. Run with Docker

Build and start services:
```sh
./setup-docker.sh
```
Or manually:
```sh
docker compose up -d --build
```

View logs:
```sh
docker compose logs -f telegram-bot
```

Stop services:
```sh
docker compose down
```

## File Structure

```
├── main.py                # Entry point, bot loop
├── telegram_bot.py        # TelegramBot class and command handling
├── services.py            # Azure AI integration
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker build
├── docker-compose.yml     # Docker Compose config
├── setup-docker.sh        # Setup script
├── .env                   # Environment variables (not committed)
├── logs/                  # Logs directory
```

## Usage

- Start a chat with your bot on Telegram.
- Use `/help` to see available commands.
- Send any message for an AI-powered response.
- Replies to messages are handled with context.

## Customization

- **AI Prompting:** Edit the `system_message` in [`get_azure_ai_response_model_router2`](services.py) for custom AI behavior.
- **Logging:** Logs are written to `logs/` and console.
- **Resource Limits:** Adjust in [`docker-compose.yml`](docker-compose.yml).

## Security

- Never commit `.env` or secrets.
- Use strong API keys and passwords.
- Run containers as non-root (already configured).

## Troubleshooting

- Check logs: `logs/` or `docker compose logs`
- Ensure environment variables are set
- For Docker issues, see [DOCKER.md](DOCKER.md)

## License

MIT License

---

**Maintained by:** [Your Name or Organization]