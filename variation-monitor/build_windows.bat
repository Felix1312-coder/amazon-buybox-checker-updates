@echo off
cd /d "%~dp0"
py -3 -m venv .buildenv
if errorlevel 1 goto fail
.buildenv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
.buildenv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name Amazon-Variation-Monitor --add-data "ui.html;." --add-data "templates.bundle.b64;." --collect-all playwright app.py
if errorlevel 1 goto fail
echo Fertig: dist\Amazon-Variation-Monitor.exe
pause
exit /b 0
:fail
echo Build fehlgeschlagen.
pause
exit /b 1
