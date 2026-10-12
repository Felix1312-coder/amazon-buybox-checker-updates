@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Bitte zuerst setup.bat ausfuehren.
 pause
 exit /b 1
)
.venv\Scripts\python.exe app.py
pause
