@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python package_update.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Amazon-Variation-Monitor --add-data "payload;payload" --hidden-import app --hidden-import selftest --collect-all playwright launcher.py
pause
