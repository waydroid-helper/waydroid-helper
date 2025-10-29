#!/bin/bash

# Launch Waydroid with Weston
# Launch Waydroid in a custom Weston window with configurable dimensions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
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
    echo -e "${CYAN}[INPUT]${NC} $1"
}

print_command() {
    echo -e "${MAGENTA}[CMD]${NC} $1"
}

# Check dependencies
print_info "Checking dependencies..."

if ! command -v waydroid &> /dev/null; then
    print_error "Waydroid is not installed or not in PATH"
    exit 1
fi

if ! command -v weston &> /dev/null; then
    print_error "Weston is not installed or not in PATH"
    print_info "Install with: sudo apt install weston"
    exit 1
fi

print_success "All dependencies found!"
echo

# Get window dimensions from user
print_info "Please enter the desired Weston window dimensions:"
echo

# Default values
DEFAULT_WIDTH=1920
DEFAULT_HEIGHT=1080

# Get width
while true; do
    print_highlight "Enter width (default: $DEFAULT_WIDTH):"
    read -p "> " width
    
    # Use default if empty
    if [ -z "$width" ]; then
        width=$DEFAULT_WIDTH
        break
    fi
    
    # Validate input
    if [[ "$width" =~ ^[0-9]+$ ]] && [ "$width" -gt 0 ] && [ "$width" -le 4096 ]; then
        break
    else
        print_error "Invalid width. Please enter a number between 1 and 4096"
    fi
done

# Get height
while true; do
    print_highlight "Enter height (default: $DEFAULT_HEIGHT):"
    read -p "> " height
    
    # Use default if empty
    if [ -z "$height" ]; then
        height=$DEFAULT_HEIGHT
        break
    fi
    
    # Validate input
    if [[ "$height" =~ ^[0-9]+$ ]] && [ "$height" -gt 0 ] && [ "$height" -le 4096 ]; then
        break
    else
        print_error "Invalid height. Please enter a number between 1 and 4096"
    fi
done

echo
print_success "Window dimensions set: ${width}x${height}"
echo

# Stop existing waydroid session
print_info "Stopping existing Waydroid session..."
if waydroid session stop 2>/dev/null; then
    print_success "Waydroid session stopped"
else
    print_warning "No active Waydroid session found (this is normal)"
fi

# Clean up any existing weston processes with waydroid socket
print_info "Cleaning up existing Weston processes..."
if pkill -f "weston.*socket=waydroid" 2>/dev/null; then
    print_success "Cleaned up existing Weston processes"
    sleep 2
else
    print_info "No existing Weston processes found"
fi

echo
print_info "Starting Weston with Waydroid..."
print_command "weston --width=$width --height=$height --socket=waydroid --shell=kiosk-shell.so"

# Start weston in background
weston --width="$width" --height="$height" --socket=waydroid --shell=kiosk-shell.so &>/dev/null &
WESTON_PID=$!

# Wait a moment for weston to start up
print_info "Waiting for Weston to initialize..."
sleep 3

# Check if weston is still running
if ! kill -0 $WESTON_PID 2>/dev/null; then
    print_error "Failed to start Weston"
    print_info "Check if you have proper graphics support and permissions"
    exit 1
fi

print_success "Weston started successfully (PID: $WESTON_PID)"

# Launch waydroid show-full-ui
print_info "Launching Waydroid full UI..."
print_command "WAYLAND_DISPLAY=waydroid XDG_SESSION_TYPE=wayland waydroid show-full-ui"

echo
print_warning "Starting Waydroid UI... This may take a few moments"
print_info "To stop: Close this terminal or press Ctrl+C"
echo

# Trap signals to clean up weston on exit
cleanup() {
    print_info "Cleaning up..."
    if kill -0 $WESTON_PID 2>/dev/null; then
        print_info "Stopping Weston (PID: $WESTON_PID)..."
        kill $WESTON_PID 2>/dev/null || true
    fi
    print_info "Stopping Waydroid session..."
    waydroid session stop 2>/dev/null || true
    print_success "Cleanup completed"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Launch waydroid show-full-ui
WAYLAND_DISPLAY=waydroid XDG_SESSION_TYPE=wayland waydroid show-full-ui
