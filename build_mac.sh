#!/bin/bash
# Builds "File Scanner.app" and a zip of it in dist/. Run on a Mac.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt pyinstaller
.venv/bin/pyinstaller --noconfirm --clean --windowed --name "File Scanner" \
  --osx-bundle-identifier com.proavl.filescanner \
  --collect-all pymediainfo --collect-submodules pillow_heif \
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml \
  --exclude-module tkinter \
  main.py
cd dist && ditto -c -k --keepParent "File Scanner.app" "File Scanner-mac.zip"
echo "Built dist/File Scanner.app and dist/File Scanner-mac.zip"
