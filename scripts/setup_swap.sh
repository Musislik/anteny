#!/usr/bin/env bash
# ==============================================================================
# Script to create and activate a 20 GB swap file on NVMe (/var/lib/docker/)
# ==============================================================================
set -euo pipefail

SWAP_FILE="${1:-/var/lib/docker/swapfile}"
SWAP_SIZE="${2:-20g}"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run with root privileges (e.g., sudo $0)" >&2
    exit 1
fi

echo "=== Setting up swap (${SWAP_SIZE}) on NVMe disk: ${SWAP_FILE} ==="

# 1. Check and clean up original /swapfile on root (SATA), if it exists
if swapon --show | grep -q "^/swapfile"; then
    echo "Disabling original /swapfile from / filesystem..."
    swapoff /swapfile 2>/dev/null || true
fi
if [ -f "/swapfile" ]; then
    echo "Removing old /swapfile (freeing space on root volume)..."
    rm -f /swapfile
fi
if grep -q "^/swapfile " /etc/fstab; then
    echo "Removing old /swapfile entry from /etc/fstab..."
    sed -i '\|^/swapfile |d' /etc/fstab
fi

# 2. Check if the target swap is already active
if swapon --show | grep -q "$SWAP_FILE"; then
    echo "Target swapfile $SWAP_FILE is already active:"
    swapon --show
    free -h
    exit 0
fi

# 3. Create swap file according to filesystem type (/var/lib/docker is ext4 on NVMe)
TARGET_DIR=$(dirname "$SWAP_FILE")
FS_TYPE=$(df -T "$TARGET_DIR" | awk 'NR==2 {print $2}')
echo "Detected filesystem for $TARGET_DIR: $FS_TYPE"

if [ -f "$SWAP_FILE" ]; then
    echo "File $SWAP_FILE already exists on disk."
    read -r -p "Do you want to overwrite and recreate it? [y/N]: " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        swapoff "$SWAP_FILE" 2>/dev/null || true
        rm -f "$SWAP_FILE"
    fi
fi

if [ ! -f "$SWAP_FILE" ]; then
    if [ "$FS_TYPE" = "btrfs" ]; then
        echo "Using btrfs mkswapfile..."
        btrfs filesystem mkswapfile --size "$SWAP_SIZE" "$SWAP_FILE"
    else
        echo "Creating 20 GB swap file on NVMe disk (using fallocate)..."
        fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=20480 status=progress
        chmod 0600 "$SWAP_FILE"
        mkswap "$SWAP_FILE"
    fi
else
    chmod 0600 "$SWAP_FILE"
fi

# 4. Set SELinux context (required on Fedora/RHEL so SELinux does not block swapon)
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
    echo "Setting SELinux context swapfile_t..."
    chcon -t swapfile_t "$SWAP_FILE" || true
    if command -v semanage >/dev/null 2>&1; then
        semanage fcontext -a -t swapfile_t "$SWAP_FILE" 2>/dev/null || true
    fi
fi

# 5. Activate swap with priority 10 (lower than zram, which has prio 100)
echo "Activating swap ($SWAP_FILE)..."
swapon -p 10 "$SWAP_FILE"

# 6. Add entry to /etc/fstab for persistent mount after reboot
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "Adding entry to /etc/fstab..."
    echo "$SWAP_FILE none swap defaults,pri=10 0 0" >> /etc/fstab
else
    echo "Entry in /etc/fstab already exists."
fi

# 7. Reload systemd units after updating fstab
systemctl daemon-reload 2>/dev/null || true

echo ""
echo "=== Done! Current swap status ==="
swapon --show
echo ""
free -h
echo ""
echo "Free space on NVMe disk (/var/lib/docker):"
df -h "$TARGET_DIR"
