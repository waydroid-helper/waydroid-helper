# Waydroid Helper - Just recipes for installation and management

# Install waydroid-helper from COPR (recommended for Fedora/rpm-ostree systems)
install-waydroid-helper:
    #!/usr/bin/env bash
    set -euo pipefail
    
    echo "Installing Waydroid Helper..."
    
    # Check if running on Fedora-based system
    if command -v rpm-ostree &> /dev/null; then
        echo "Installing from COPR repository (recommended method)..."
        
        # Check if waydroid-helper is installed in the CURRENT booted deployment
        if rpm -q waydroid-helper &>/dev/null; then
            echo "✓ Waydroid Helper is already installed in the current deployment!"
        else
            # Check if COPR repo is already added
            if ! grep -q "copr:copr.fedorainfracloud.org:cuteneko:waydroid-helper" /etc/yum.repos.d/cuteneko-waydroid-helper.repo 2>/dev/null; then
                echo "Adding COPR repository..."
                curl -Lo /tmp/cuteneko-waydroid-helper-fedora.repo \
                    "https://copr.fedorainfracloud.org/coprs/cuteneko/waydroid-helper/repo/fedora/cuteneko-waydroid-helper-fedora.repo"
                sudo mv /tmp/cuteneko-waydroid-helper-fedora.repo /etc/yum.repos.d/
            fi
            
            echo "Installing waydroid-helper"
            rpm-ostree install --apply-live --allow-inactive waydroid-helper bindfs
            
            echo "✓ Waydroid Helper installed successfully!"
        fi
        
    elif command -v dnf &> /dev/null; then
        echo "Detected DNF-based system"
        echo "Installing from COPR repository..."
        sudo dnf copr enable -y cuteneko/waydroid-helper
        sudo dnf install -y waydroid-helper bindfs
        
        echo "✓ Waydroid Helper installed successfully!"
        
    else
        echo "Error: This system is not Fedora-based."
        exit 1
    fi
    
    # Enable systemd services
    echo "Enabling systemd services..."
    systemctl --user enable waydroid-monitor.service --now || true
    sudo systemctl enable waydroid-mount.service --now || true
    
    echo ""
    echo "You can now run 'waydroid-helper' to start the application."

# Build and install waydroid-helper from source
uninstall-waydroid-helper:
    #!/usr/bin/env bash
    set -euo pipefail
    
    echo "Uninstalling Waydroid Helper..."
    
    # Disable systemd services
    echo "Disabling systemd services..."
    systemctl --user disable waydroid-monitor.service --now 2>/dev/null || true
    sudo systemctl disable waydroid-mount.service --now 2>/dev/null || true
    
    # Try package manager first
    if command -v rpm-ostree &> /dev/null; then
        echo "Removing via rpm-ostree..."
        rpm-ostree uninstall waydroid-helper || true
        
    elif command -v dnf &> /dev/null; then
        echo "Removing via DNF..."
        sudo dnf remove -y waydroid-helper || true
    fi
    
    echo "✓ Waydroid Helper uninstalled!"

# Update waydroid-helper to the latest version
update-waydroid-helper:
    #!/usr/bin/env bash
    set -euo pipefail
    
    echo "Updating Waydroid Helper..."
    
    if command -v rpm-ostree &> /dev/null; then
        echo "Updating via rpm-ostree..."
        
        # First, update the repo metadata
        rpm-ostree refresh-md
        
        # Check if update is available
        if rpm-ostree upgrade --check 2>/dev/null | grep -q waydroid-helper; then
            echo "Update available, upgrading..."
            rpm-ostree upgrade
            echo "✓ Waydroid Helper updated successfully!"
        else
            echo "✓ Waydroid Helper is already at the latest version!"
        fi
        
    elif command -v dnf &> /dev/null; then
        echo "Updating via DNF..."
        sudo dnf upgrade -y waydroid-helper
        echo "✓ Waydroid Helper updated successfully!"

    else
        echo "Error: No supported package manager found."
        echo "Please update manually or reinstall from source."
        exit 1
    fi
    
    # Restart services to apply updates
    echo "Restarting systemd services..."
    systemctl --user restart waydroid-monitor.service 2>/dev/null || true
    sudo systemctl restart waydroid-mount.service 2>/dev/null || true
    
    echo ""
    echo "Update complete! You may need to restart waydroid-helper if it's running."

# Show waydroid-helper info
info-waydroid-helper:
    @echo "Waydroid Helper - GTK4/Libadwaita GUI for Waydroid"
    @echo "=================================================="
    @echo "Version: 0.2.9"
    @echo "Repository: https://github.com/waydroid-helper/waydroid-helper"
    @echo ""
    @echo "Available commands:"
    @echo "  install-waydroid-helper        - Install from COPR (Fedora/rpm-ostree)"
    @echo "  update-waydroid-helper         - Update to the latest version"
    @echo "  uninstall-waydroid-helper      - Uninstall Waydroid Helper"
    @echo "  info-waydroid-helper           - Show this information"
    @echo ""
    @echo "Recommended: Use 'install-waydroid-helper' on Fedora-based systems"
