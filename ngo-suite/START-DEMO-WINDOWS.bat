@echo off
cd /d "%~dp0"
echo Starting NGO Suite with SAMPLE DATA on every page.
echo Open http://127.0.0.1:8021 in your browser.
echo Username: admin   Password: ChangeMe123
echo (Your real data is not touched. Delete data\demo.db to reset the sample data.)
py run.py --demo --port 8021
pause
