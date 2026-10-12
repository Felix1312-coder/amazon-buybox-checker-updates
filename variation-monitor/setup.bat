@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 goto fail
echo Installation abgeschlossen. Jetzt start.bat oeffnen.
pause
exit /b 0
:fail
echo Installation fehlgeschlagen. Python 3.10 oder neuer und Internet werden benoetigt.
pause
exit /b 1
