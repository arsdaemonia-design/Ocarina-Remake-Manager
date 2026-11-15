#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name OcarinaRemakeManager-Linux-x64 \
    --add-data "i18n:i18n" \
    --collect-submodules PIL \
    --hidden-import PIL.Image \
    --distpath dist_linux \
    --workpath build_linux_tmp \
    app.py

chmod +x "dist_linux/OcarinaRemakeManager-Linux-x64"
tar -czf "dist_linux/OcarinaRemakeManager-Linux-x64.tar.gz" -C dist_linux "OcarinaRemakeManager-Linux-x64"
rm -rf build_linux_tmp OcarinaRemakeManager-Linux-x64.spec
echo "Single-file Linux binary built at dist_linux/OcarinaRemakeManager-Linux-x64"
