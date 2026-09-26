@echo off
setlocal
cd /d "%~dp0"
echo Starting Sogility GO Elite Athlete Assessment workflow...
if not exist "output\.venv\Scripts\python.exe" (
    echo Project virtual environment not found: output\.venv
    echo Create it and install requirements before running this launcher.
    pause
    exit /b 1
)
set "MPLCONFIGDIR=%CD%\output\matplotlib-cache"
"output\.venv\Scripts\python.exe" -m src.main
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" pause
exit /b %APP_EXIT_CODE%
