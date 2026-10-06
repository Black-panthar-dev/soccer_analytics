@echo off
setlocal
cd /d "%~dp0"
echo Generating Sogility GO athlete reports...
if not exist "output\.venv\Scripts\python.exe" (
    echo Project virtual environment not found: output\.venv
    echo Create it and install requirements before running this launcher.
    pause
    exit /b 1
)
set "MPLCONFIGDIR=%CD%\output\matplotlib-cache"
"output\.venv\Scripts\python.exe" -m src.batch_processor
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" pause
exit /b %APP_EXIT_CODE%
