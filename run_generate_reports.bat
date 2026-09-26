@echo off
setlocal
cd /d "%~dp0"
if exist "output\.venv\Scripts\python.exe" (
  set "REPORT_PYTHON=output\.venv\Scripts\python.exe"
) else (
  set "REPORT_PYTHON=python"
)
set "PYTHONPATH=."
set "MPLCONFIGDIR=%CD%\output\matplotlib"
echo Generating final athlete reports...
"%REPORT_PYTHON%" -m src.batch_processor
set "REPORT_EXIT_CODE=%ERRORLEVEL%"
if "%REPORT_EXIT_CODE%"=="0" echo Report generation completed successfully.
if not "%REPORT_EXIT_CODE%"=="0" echo Report generation completed with failures. See output\final\generation_log.txt
exit /b %REPORT_EXIT_CODE%
