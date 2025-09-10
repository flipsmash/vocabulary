# WSL2 + Supabase Setup Script for Windows
# Run this in PowerShell as Administrator

Write-Host "Setting up WSL2 + Supabase for Vocabulary Database Migration..." -ForegroundColor Green

# Step 1: Install WSL2 and Ubuntu 22.04
Write-Host "`nStep 1: Installing WSL2 and Ubuntu 22.04..." -ForegroundColor Yellow
wsl --install Ubuntu-22.04
wsl --set-default-version 2
wsl --set-version Ubuntu-22.04 2

# Step 2: Configure WSL2 resource limits
Write-Host "`nStep 2: Configuring WSL2 resources..." -ForegroundColor Yellow
$wslConfigPath = "$env:USERPROFILE\.wslconfig"
$wslConfig = @"
[wsl2]
memory=16GB
processors=6
swap=4GB
localhostForwarding=true
nestedVirtualization=true
kernelCommandLine=cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1
"@

$wslConfig | Out-File -FilePath $wslConfigPath -Encoding UTF8
Write-Host "WSL2 config written to $wslConfigPath" -ForegroundColor Green

# Step 3: Create setup script for Ubuntu
Write-Host "`nStep 3: Creating Ubuntu setup script..." -ForegroundColor Yellow
$ubuntuSetupScript = @"
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
sudo usermod -aG docker `$USER
rm get-docker.sh

# Install Docker Compose (latest version)
echo "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-`$(uname -s)-`$(uname -m)" -o /usr/local/bin/docker-compose
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
echo "Please restart WSL2 and run the Supabase setup script"
echo "=========================================="
"@

$scriptPath = "C:\temp\ubuntu_setup.sh"
New-Item -Path "C:\temp" -ItemType Directory -Force
$ubuntuSetupScript | Out-File -FilePath $scriptPath -Encoding UTF8

Write-Host "`nSetup scripts created. Next steps:" -ForegroundColor Green
Write-Host "1. Restart your computer to complete WSL2 installation" -ForegroundColor White
Write-Host "2. Open WSL2 Ubuntu and run: bash /mnt/c/temp/ubuntu_setup.sh" -ForegroundColor White
Write-Host "3. Restart WSL2: wsl --shutdown && wsl" -ForegroundColor White
Write-Host "4. Run the Supabase setup script (will be created next)" -ForegroundColor White

Write-Host "`nPress any key when you've completed the above steps..." -ForegroundColor Yellow
Read-Host