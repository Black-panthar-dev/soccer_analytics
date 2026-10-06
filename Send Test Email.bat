@echo off
setlocal
cd /d "%~dp0"
title Sogility GO - Send Test Email

echo --------------------------------------------------
echo SOGILITY GO - SEND ONE TEST EMAIL
echo --------------------------------------------------
echo.
echo This action sends exactly one TEST email to the configured
echo test recipient. It never sends to a parent recipient.
echo.

if not exist "config\google_token.json" goto missing_authorization

set "SOGILITY_PYTHON="
if exist "output\.venv\Scripts\python.exe" set "SOGILITY_PYTHON=output\.venv\Scripts\python.exe"
if not defined SOGILITY_PYTHON if exist ".venv\Scripts\python.exe" set "SOGILITY_PYTHON=.venv\Scripts\python.exe"
if not defined SOGILITY_PYTHON where py >nul 2>nul && set "SOGILITY_PYTHON=py -3"
if not defined SOGILITY_PYTHON where python >nul 2>nul && set "SOGILITY_PYTHON=python"
if not defined SOGILITY_PYTHON goto missing_components

%SOGILITY_PYTHON% -c "import google.auth, google_auth_oauthlib, googleapiclient" >nul 2>nul
if errorlevel 1 goto missing_components

%SOGILITY_PYTHON% -c "import json,sys; from pathlib import Path; from src.email_planner import is_valid_email; s=json.loads(Path('config/email_settings.json').read_text(encoding='utf-8')); sys.exit(0 if is_valid_email(str(s.get('test_recipient') or '').strip()) else 1)" >nul 2>nul
if errorlevel 1 goto missing_test_recipient

echo Press any key to send one test email...
pause >nul
%SOGILITY_PYTHON% -m src.email_send_cli --test-send --project-root "%CD%"
if errorlevel 1 goto test_failed
echo.
echo SUCCESS: One test email was sent to the configured test recipient.
echo.
pause
exit /b 0

:missing_authorization
echo Google email authorization is missing.
echo First double-click "Authorize Google Email.bat".
echo.
pause
exit /b 1

:missing_components
echo The test email could not start because required application
echo components are missing. Please contact the developer.
echo.
pause
exit /b 1

:missing_test_recipient
echo A valid test recipient is not configured.
echo The test launcher will not use a production recipient.
echo Please contact the developer.
echo.
pause
exit /b 1

:test_failed
echo.
echo TEST EMAIL NOT SENT
echo Please check the message above or contact the developer.
echo.
pause
exit /b 1
