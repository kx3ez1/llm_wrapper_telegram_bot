# Docker Deployment Guide

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed
- Telegram Bot Token from [@BotFather](https://t.me/botfather)
- Azure AI API Key

### 2. Setup Environment
```bash
# Copy and edit environment file
cp .env.example .env
# Edit .env with your actual tokens
```

### 3. Run with Docker Compose
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f telegram-bot

# Stop services
docker-compose down
```

## File Structure
```
├── Dockerfile                 # Main application container
├── docker-compose.yml         # Development setup
├── docker-compose.prod.yml    # Production setup
├── .dockerignore              # Docker ignore file
├── setup-docker.sh           # Automated setup script
└── .env                       # Environment variables
```

## Available Services

### Development (`docker-compose.yml`)
- **telegram-bot**: Main bot application
- **redis**: Optional caching and session storage

### Production (`docker-compose.prod.yml`)
- **telegram-bot**: Production-optimized bot
- **redis**: Secured Redis with password
- **nginx**: Reverse proxy for webhooks
- **fluentd**: Log aggregation

## Commands

### Development
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart telegram-bot

# Stop all services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

### Production
```bash
# Start production services
docker-compose -f docker-compose.prod.yml up -d

# Scale bot instances
docker-compose -f docker-compose.prod.yml up -d --scale telegram-bot=3

# Update with zero downtime
docker-compose -f docker-compose.prod.yml up -d --no-deps telegram-bot
```

### Maintenance
```bash
# Clean up unused containers/images
docker system prune -a

# View resource usage
docker stats

# Export logs
docker-compose logs --no-color > bot-logs.txt

# Backup Redis data
docker exec llm-bot-redis redis-cli BGSAVE
```

## Environment Variables

### Required
```env
TELEGRAM_BOT_TOKEN=your_bot_token
AZURE_API_KEY=your_azure_key
```

### Optional
```env
ENVIRONMENT=production
REDIS_PASSWORD=secure_password
LOG_LEVEL=INFO
```

## Security Notes

1. **Never commit .env files** to version control
2. **Use strong Redis passwords** in production
3. **Run containers as non-root user** (already configured)
4. **Limit container resources** (configured in compose files)
5. **Use HTTPS for webhooks** in production

## Monitoring

### Health Checks
The bot includes built-in health checks that verify:
- Telegram API connectivity
- Azure AI service availability

### Logs
- Application logs: `./logs/`
- Container logs: `docker-compose logs`
- System logs: `journalctl -u docker`

### Metrics
Consider adding:
- Prometheus for metrics collection
- Grafana for visualization
- Alert manager for notifications

## Troubleshooting

### Common Issues

1. **Bot not starting**
   ```bash
   # Check logs
   docker-compose logs telegram-bot
   
   # Verify environment variables
   docker-compose exec telegram-bot env | grep -E "(TELEGRAM|AZURE)"
   ```

2. **Connection issues**
   ```bash
   # Test network connectivity
   docker-compose exec telegram-bot ping api.telegram.org
   
   # Check DNS resolution
   docker-compose exec telegram-bot nslookup api.telegram.org
   ```

3. **Resource constraints**
   ```bash
   # Monitor resource usage
   docker stats
   
   # Increase memory limits in docker-compose.yml
   ```

4. **Permission issues**
   ```bash
   # Fix log directory permissions
   sudo chown -R $(id -u):$(id -g) logs/
   ```

## Production Deployment

1. **Use production compose file**
2. **Set up proper DNS and SSL certificates**
3. **Configure monitoring and alerting**
4. **Set up automated backups**
5. **Implement log rotation**
6. **Use secrets management for sensitive data**

## Performance Optimization

1. **Use webhooks instead of polling** (requires HTTPS)
2. **Enable Redis caching** for frequent requests
3. **Scale horizontally** with multiple bot instances
4. **Use CDN** for static content
5. **Optimize Docker images** with multi-stage builds