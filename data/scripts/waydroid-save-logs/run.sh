#!/bin/bash

# Save Waydroid Logs
# Capture and save Waydroid system logs to a file for debugging

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_highlight() {
    echo -e "${CYAN}[LOG]${NC} $1"
}

# Check if waydroid is available
if ! command -v waydroid &> /dev/null; then
    print_error "Waydroid is not installed or not in PATH"
    exit 1
fi

# Check if user has sudo privileges
if ! sudo -n true 2>/dev/null; then
    print_warning "This script requires sudo privileges to run waydroid logcat"
    print_info "You may be prompted for your password"
fi

# Create log directory if it doesn't exist
LOG_DIR="$HOME/waydroid-logs"
mkdir -p "$LOG_DIR"

# Generate log filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/waydroid_logcat_$TIMESTAMP.txt"

print_info "Starting Waydroid log capture..."
print_highlight "Log file: $LOG_FILE"

echo
print_info "Log capture is running. Press Ctrl+C to stop and exit."
print_warning "When you close this terminal, logging will automatically stop."
echo

# Trap signals to clean up on exit
cleanup() {
    print_info "Stopping logcat and cleaning up..."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start logging - this will run in foreground and exit when terminal closes
sudo waydroid logcat > "$LOG_FILE" 2>&1
sudo chmod 666 "$LOG_FILE"
