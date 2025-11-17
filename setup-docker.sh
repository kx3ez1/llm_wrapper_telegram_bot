#!/bin/bash

# Telegram Bot Docker Setup Script
set -e

echo "🐳 Setting up Telegram Bot with Docker..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found. Creating template..."
    cat > .env << EOF
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Azure AI Configuration
AZURE_API_KEY=your_azure_api_key_here

# Optional: Redis Configuration
REDIS_PASSWORD=your_redis_password_here

# Optional: Environment
ENVIRONMENT=development
EOF
    print_warning "Please edit .env file with your actual tokens and keys"
    exit 1
fi

# Create logs directory
mkdir -p logs
print_status "Created logs directory"

# Build and start services
print_status "Building Docker images..."
docker compose build

print_status "Starting services..."
docker compose up -d

print_status "Waiting for services to be ready..."
sleep 10

# Check if services are running
if docker compose ps | grep -q "Up"; then
    print_status "✅ Services started successfully!"
    echo ""
    echo "📊 Service Status:"
    docker compose ps
    echo ""
    echo "📝 To view logs:"
    echo "   docker compose logs -f telegram-bot"
    echo ""
    echo "🛑 To stop services:"
    echo "   docker compose down"
    echo ""
    echo "🔄 To restart services:"
    echo "   docker compose restart"
else
    print_error "❌ Failed to start services"
    echo "Check logs with: docker compose logs"
    exit 1
fi