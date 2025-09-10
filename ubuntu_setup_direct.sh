#!/bin/bash
set -e

echo "=========================================="
echo "Setting up Ubuntu 22.04 for Supabase"
echo "=========================================="

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install essential packages
echo "Installing essential packages..."
sudo apt install -y curl wget git vim htop postgresql-client python3-pip

# Install Docker
echo "Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
rm get-docker.sh

# Install Docker Compose (latest version)
echo "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install Node.js (for Supabase CLI if needed)
echo "Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Python packages for migration
echo "Installing Python packages..."
pip3 install psycopg2-binary mysql-connector-python pandas tqdm

# Create directory structure
echo "Creating directory structure..."
mkdir -p ~/supabase-setup
mkdir -p ~/vocabulary-migration

echo "=========================================="
echo "Ubuntu setup complete!"
echo "Please restart WSL2: exit, then wsl --shutdown && wsl"
echo "Then run: bash /mnt/c/Users/Brian/vocabulary/supabase_setup.sh"
echo "=========================================="