@echo off
rem Builds "File Scanner.exe" in dist\. Run on Windows with Python 3.10+ installed (python.org).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --onefile --name "File Scanner" ^
  --collect-all pymediainfo --collect-submodules pillow_heif ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtPdf --exclude-module PySide6.QtMultimedia --exclude-module tkinter ^
  main.py
echo Built "dist\File Scanner.exe"
pause
