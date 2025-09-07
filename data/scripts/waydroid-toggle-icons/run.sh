#!/bin/bash

# Toggle Waydroid App Icons
# Show or hide Waydroid application icons from the desktop launcher

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

# Find Waydroid desktop files (exclude Waydroid.desktop)
DESKTOP_FILES=~/.local/share/applications/waydroid.*.desktop

print_info "Checking for Waydroid desktop files..."

if ! ls $DESKTOP_FILES 1> /dev/null 2>&1; then
    print_error "No Waydroid desktop files found in ~/.local/share/applications/"
    print_info "Make sure Waydroid is properly installed and has created application shortcuts"
    exit 1
fi

# Filter out Waydroid.desktop (with capital W) and count valid files
VALID_FILES=()
for file in $DESKTOP_FILES; do
    # Exclude Waydroid.desktop (capital W)
    if [[ "$(basename "$file")" != "Waydroid.desktop" ]]; then
        VALID_FILES+=("$file")
    fi
done

if [ ${#VALID_FILES[@]} -eq 0 ]; then
    print_error "No valid Waydroid app desktop files found (excluding Waydroid.desktop)"
    print_info "Only found system Waydroid.desktop file, which should not be modified"
    exit 1
fi

FILE_COUNT=${#VALID_FILES[@]}
print_info "Found $FILE_COUNT Waydroid app desktop file(s) (excluding Waydroid.desktop)"

# Check current status by looking for NoDisplay=true in valid files
HIDDEN_COUNT=0
for file in "${VALID_FILES[@]}"; do
    if grep -q "NoDisplay=true" "$file" 2>/dev/null; then
        HIDDEN_COUNT=$((HIDDEN_COUNT + 1))
    fi
done

if [ "$HIDDEN_COUNT" -gt 0 ]; then
    # Icons are currently hidden, show them
    print_info "Waydroid icons are currently HIDDEN. Showing them..."
    
    for file in "${VALID_FILES[@]}"; do
        if grep -q "NoDisplay=true" "$file"; then
            sed -i '/NoDisplay=true/d' "$file"
            print_success "Removed NoDisplay from $(basename "$file")"
        fi
    done
    
    print_success "Waydroid application icons are now VISIBLE in the launcher"
    
else
    # Icons are currently visible, hide them
    print_info "Waydroid icons are currently VISIBLE. Hiding them..."
    
    for file in "${VALID_FILES[@]}"; do
        if ! grep -q "NoDisplay=true" "$file"; then
            # Add NoDisplay=true after the Actions line, or at the end if no Actions line
            if grep -q "Actions=" "$file"; then
                sed -i '/Actions=/a NoDisplay=true' "$file"
            else
                echo "NoDisplay=true" >> "$file"
            fi
            print_success "Added NoDisplay to $(basename "$file")"
        fi
    done
    
    print_success "Waydroid application icons are now HIDDEN from the launcher"
fi

print_info "Operation completed successfully!"
print_warning "Note: You may need to refresh your desktop environment or log out/in to see the changes"
