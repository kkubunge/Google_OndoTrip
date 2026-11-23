@echo off
setlocal
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
for /f %%i in ('.venv\Scripts\python.exe -c "import datetime;print(datetime.date.today().strftime('%%Y%%m%%d'))"') do set TODAY=%%i
echo ============================================================ >> "logs\daily_%TODAY%.log"
echo [%DATE% %TIME%] OndoTrip Daily Auto Start >> "logs\daily_%TODAY%.log"
".venv\Scripts\python.exe" main.py --mode auto --count 5 %* >> "logs\daily_%TODAY%.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%DATE% %TIME%] OndoTrip Daily Auto End (exit=%EXIT_CODE%) >> "logs\daily_%TODAY%.log"
exit /b %EXIT_CODE%
