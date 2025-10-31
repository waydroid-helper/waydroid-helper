#!/bin/bash

# Workaround Android Directory Permissions
# Set 777 permissions for Android data and obb directories to workaround black screen issues in some games

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Check if waydroid is available
if ! command -v waydroid &> /dev/null; then
    print_error "Waydroid is not installed or not in PATH"
    exit 1
fi

# Check if Waydroid is running
if ! waydroid status 2>/dev/null | grep -qP "Session:.*RUNNING"; then
    print_error "Waydroid is not running"
    print_info "Please start Waydroid first with: waydroid session start"
    exit 1
fi

print_info "This may help resolve black screen issues in some games"
print_warning "This script requires sudo privileges to modify Android directory permissions"
print_info "You may be prompted for your password"

print_info "Starting Android directory permissions workaround..."
echo

# Array of directories to fix
DIRS=(
    "/sdcard/Android"
    "/data/media/0/Android"
    "/sdcard/Android/data"
    "/data/media/0/Android/obb"
    "/mnt/*/*/*/*/Android/data"
    "/mnt/*/*/*/*/Android/obb"
)

# Fix permissions for each directory
for dir in "${DIRS[@]}"; do
    print_info "Setting permissions: $dir"
    if sudo waydroid shell -- sh -c "chmod 777 -R $dir" 2>/dev/null; then
        print_success "Completed: $dir"
    else
        print_warning "Skipped (may not exist): $dir"
    fi
done

echo
print_success "Android directory permissions workaround completed!"
print_info "All directories have been set to 777 permissions"

