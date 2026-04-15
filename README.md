# LLM Wrapper Telegram Bot

A fast, production-ready Telegram bot using the OpenAI SDK pointed at a custom Azure endpoint. Returns markdown-formatted AI responses with optional password protection, Docker support, and concurrent message processing.

## Features

- **Telegram Bot API** integration via long-polling
- **OpenAI SDK** → custom Azure endpoint backend
- Markdown formatting in responses
- Command handling: `/start`, `/help`, `/about`, `/ping`, `/status`, `/clear`, `/logout`
- Optional password protection (`BOT_PASSWORD`)
- Reply-with-context: replying to a message sends both messages as context to AI
- Auto-splits responses longer than 4096 chars
- Error handling and rotating file logging
- Docker & Docker Compose support
- Concurrent message processing (ThreadPoolExecutor)

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Docker & Docker Compose (for containerized deployment)
- Telegram Bot Token ([@BotFather](https://t.me/botfather))
- Azure OpenAI API key and endpoint

### 2. Setup Environment

Create `.env` in the project root:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_AZURE_API_KEY=your_azure_api_key
OPENAI_AZURE_ENDPOINT=https://your-resource.openai.azure.com/openai/v1
OPENAI_AZURE_DEPLOYMENT=gpt-5-nano

# Optional
BOT_PASSWORD=your_bot_password        # Enables password protection
LOG_LEVEL=INFO                        # DEBUG, INFO, WARNING, ERROR
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

Or use the run script:
```sh
./run.sh
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

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `OPENAI_AZURE_API_KEY` | Yes | — | Azure OpenAI API key |
| `OPENAI_AZURE_ENDPOINT` | No | `https://customwrapper1.openai.azure.com/openai/v1` | Azure endpoint URL |
| `OPENAI_AZURE_DEPLOYMENT` | No | `gpt-5-nano` | Model deployment name |
| `BOT_PASSWORD` | No | — | Enables password protection if set |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

## File Structure

```
├── main.py                # Entry point, bot loop, concurrent processing
├── telegram_bot.py        # TelegramBot class, command handling, auth
├── services.py            # OpenAI/Azure AI integration
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker build
├── docker-compose.yml     # Docker Compose config
├── setup-docker.sh        # Docker setup script
├── run.sh                 # Local run script
├── .env                   # Environment variables (not committed)
├── logs/                  # Rotating log files
```

## Usage

- Start a chat with your bot on Telegram.
- Use `/help` to see available commands.
- Send any message for an AI-powered response.
- Reply to any message — the bot sends both messages as context to the AI.

## Authentication

If `BOT_PASSWORD` is set, users must authenticate before the bot responds:

1. Send `/start` — bot prompts for password
2. Send the password — bot grants access
3. Send `/logout` — revokes access

Without `BOT_PASSWORD`, the bot is publicly accessible.

## Customization

- **AI Prompting:** Edit the `system_message` parameter in [`get_openai_response`](services.py) for custom AI behavior.
- **Model:** Set `OPENAI_AZURE_DEPLOYMENT` in `.env`.
- **Logging:** Logs rotate at 5 MB, 3 backups, written to `logs/bot.log` and console.
- **Resource Limits:** Adjust memory/CPU in [`docker-compose.yml`](docker-compose.yml).
- **Concurrency:** Change `max_workers` in `main.py` (default: 5 threads).

## Security

- Never commit `.env` or secrets.
- Run containers as non-root (already configured).
- Use `BOT_PASSWORD` to restrict access to authorized users.

## Troubleshooting

- Check logs: `logs/bot.log` or `docker compose logs -f telegram-bot`
- Ensure all required environment variables are set
- For Docker issues, see [DOCKER.md](DOCKER.md)

## License

MIT License