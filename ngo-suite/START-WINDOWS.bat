@echo off
cd /d "%~dp0"
echo Starting NGO Suite with YOUR data. Open http://127.0.0.1:8020 in your browser.
echo First time only: the admin password is shown below. You will be asked to change it.
echo To see sample data instead, close this and run START-DEMO-WINDOWS.bat
py run.py --port 8020
pause
