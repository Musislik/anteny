#!/usr/bin/env bash
# ==============================================================================
# Skript pro vytvoření a aktivaci 20 GB swap souboru na NVMe (/var/lib/docker/)
# ==============================================================================
set -euo pipefail

SWAP_FILE="${1:-/var/lib/docker/swapfile}"
SWAP_SIZE="${2:-20g}"

if [ "$(id -u)" -ne 0 ]; then
    echo "CHYBA: Tento skript musí být spuštěn s oprávněním roota (např. sudo $0)" >&2
    exit 1
fi

echo "=== Nastavení swapu (${SWAP_SIZE}) na NVMe disku: ${SWAP_FILE} ==="

# 1. Kontrola a vyčištění původního /swapfile na rootu (SATA), pokud existuje
if swapon --show | grep -q "^/swapfile"; then
    echo "Vypínám původní /swapfile ze souborového systému /..."
    swapoff /swapfile 2>/dev/null || true
fi
if [ -f "/swapfile" ]; then
    echo "Odstraňuji starý /swapfile (uvolňuji místo na root svazku)..."
    rm -f /swapfile
fi
if grep -q "^/swapfile " /etc/fstab; then
    echo "Odstraňuji starý /swapfile z /etc/fstab..."
    sed -i '\|^/swapfile |d' /etc/fstab
fi

# 2. Kontrola, zda již není cílový swap aktivní
if swapon --show | grep -q "$SWAP_FILE"; then
    echo "Cílový swapfile $SWAP_FILE je již aktivní:"
    swapon --show
    free -h
    exit 0
fi

# 3. Vytvoření swap souboru dle typu souborového systému (/var/lib/docker je ext4 na NVMe)
TARGET_DIR=$(dirname "$SWAP_FILE")
FS_TYPE=$(df -T "$TARGET_DIR" | awk 'NR==2 {print $2}')
echo "Detekován souborový systém pro $TARGET_DIR: $FS_TYPE"

if [ -f "$SWAP_FILE" ]; then
    echo "Soubor $SWAP_FILE již existuje na disku."
    read -r -p "Přejete si jej přepsat a znovu vytvořit? [y/N]: " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        swapoff "$SWAP_FILE" 2>/dev/null || true
        rm -f "$SWAP_FILE"
    fi
fi

if [ ! -f "$SWAP_FILE" ]; then
    if [ "$FS_TYPE" = "btrfs" ]; then
        echo "Používám btrfs mkswapfile..."
        btrfs filesystem mkswapfile --size "$SWAP_SIZE" "$SWAP_FILE"
    else
        echo "Vytvářím 20 GB soubor na NVMe disku (pomocí fallocate)..."
        fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=20480 status=progress
        chmod 0600 "$SWAP_FILE"
        mkswap "$SWAP_FILE"
    fi
else
    chmod 0600 "$SWAP_FILE"
fi

# 4. Nastavení SELinux kontextu (klíčové pro Fedora/RHEL, aby SELinux neblokoval swapon)
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
    echo "Nastavuji SELinux kontext swapfile_t..."
    chcon -t swapfile_t "$SWAP_FILE" || true
    if command -v semanage >/dev/null 2>&1; then
        semanage fcontext -a -t swapfile_t "$SWAP_FILE" 2>/dev/null || true
    fi
fi

# 5. Aktivace swapu s prioritou 10 (nižší než zram, který má prio 100)
echo "Aktivuji swap ($SWAP_FILE)..."
swapon -p 10 "$SWAP_FILE"

# 6. Přidání do /etc/fstab pro trvalé připojení po restartu
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "Přidávám záznam do /etc/fstab..."
    echo "$SWAP_FILE none swap defaults,pri=10 0 0" >> /etc/fstab
else
    echo "Záznam v /etc/fstab již existuje."
fi

# 7. Reload systemd jednotek po úpravě fstab
systemctl daemon-reload 2>/dev/null || true

echo ""
echo "=== Hotovo! Aktuální stav swapu ==="
swapon --show
echo ""
free -h
echo ""
echo "Volné místo na NVMe disku (/var/lib/docker):"
df -h "$TARGET_DIR"
