#!/bin/bash

# Script to set up proper permissions and run the Docker container

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

echo "🔧 Setting up permissions for Docker container..."

# Remove old logs directory if it exists
if [ -d "$LOGS_DIR" ]; then
    echo "🗑️  Cleaning old logs directory..."
    sudo rm -rf "$LOGS_DIR"
fi

# Create logs directory with full permissions
echo "📁 Creating logs directory with proper permissions..."
mkdir -p "$LOGS_DIR"
chmod 777 "$LOGS_DIR"

# Stop any existing containers
echo "🛑 Stopping any existing containers..."
sudo docker compose down 2>/dev/null || true

# Remove old images to ensure fresh build
echo "🗑️  Removing old Docker images..."
sudo docker compose rm -f 2>/dev/null || true

# Build the Docker image
echo "🏗️  Building Docker image..."
sudo docker compose build --no-cache

# Start the container
echo "🚀 Starting the container..."
sudo docker compose up -d

