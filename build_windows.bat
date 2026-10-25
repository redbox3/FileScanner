@echo off
rem Builds "File Scanner.exe" in dist\. Run on Windows with 64-bit Python 3.9+ installed (python.org).
setlocal
cd /d "%~dp0"

set "CHECK=import sys, struct; sys.exit(0 if sys.version_info >= (3, 9) and struct.calcsize('P') == 8 else 1)"

rem Find a suitable Python: "python" on PATH first, then the py launcher.
set "PY="
python -c "%CHECK%" >nul 2>nul && set "PY=python"
if not defined PY py -3.12 -c "%CHECK%" >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 -c "%CHECK%" >nul 2>nul && set "PY=py -3"
if not defined PY goto :nopython
echo Using:
%PY% -c "import sys; print(sys.executable, sys.version)"

rem Rebuild .venv if it was made with an old or 32-bit Python.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python -c "%CHECK%" >nul 2>nul || (
    echo Existing .venv uses an unsupported Python. Recreating it...
    rmdir /s /q .venv
  )
)
if not exist .venv\Scripts\python.exe (
  if exist .venv rmdir /s /q .venv
  %PY% -m venv .venv || goto :fail
)

.venv\Scripts\python -m pip install -q --upgrade pip || goto :fail
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller || goto :fail
.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --onefile --name "File Scanner" ^
  --collect-all pymediainfo --collect-submodules pillow_heif ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  --exclude-module tkinter ^
  main.py || goto :fail
if not exist "dist\File Scanner.exe" goto :fail

echo.
echo Built "dist\File Scanner.exe"
pause
exit /b 0

:nopython
echo.
echo ERROR: 64-bit Python 3.9 or newer was not found.
echo Install Python 3.12 64-bit from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH" during setup, then open a new
echo Command Prompt and run this script again.
pause
exit /b 1

:fail
echo.
echo ERROR: The build failed. See the messages above. No exe was built.
pause
exit /b 1
