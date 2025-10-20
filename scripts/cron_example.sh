#!/bin/bash
# Example cron script for vocabulary rarity maintenance
# Copy and customize for your cron setup

# Set up environment
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
VOCAB_DIR="/mnt/c/Users/Brian/vocabulary"
VENV_PYTHON="$VOCAB_DIR/.venv/bin/python"
SCRIPT="$VOCAB_DIR/scripts/maintain_rarity.py"
LOG_DIR="/var/log/vocabulary"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Change to vocabulary directory
cd "$VOCAB_DIR" || exit 1

# Run maintenance script
"$VENV_PYTHON" "$SCRIPT" --silent

# Exit with script's exit code
exit $?
