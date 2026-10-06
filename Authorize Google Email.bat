@echo off
setlocal
cd /d "%~dp0"
title Sogility GO - Google Email Authorization

echo --------------------------------------------------
echo SOGILITY GO - GOOGLE EMAIL AUTHORIZATION
echo --------------------------------------------------
echo.
echo This will open Google in your browser.
echo.
echo Please sign in using:
echo.
echo   your approved Google Workspace account
echo.
echo Your Google password is entered only on Google's website.
echo The Sogility application does not see or store your password.
echo.

if not exist "config\google_credentials.json" goto missing_components

set "SOGILITY_PYTHON="
if exist "output\.venv\Scripts\python.exe" set "SOGILITY_PYTHON=output\.venv\Scripts\python.exe"
if not defined SOGILITY_PYTHON if exist ".venv\Scripts\python.exe" set "SOGILITY_PYTHON=.venv\Scripts\python.exe"
if not defined SOGILITY_PYTHON where py >nul 2>nul && set "SOGILITY_PYTHON=py -3"
if not defined SOGILITY_PYTHON where python >nul 2>nul && set "SOGILITY_PYTHON=python"
if not defined SOGILITY_PYTHON goto missing_components

%SOGILITY_PYTHON% -c "import google.auth, google_auth_oauthlib, googleapiclient" >nul 2>nul
if errorlevel 1 goto missing_components

echo Press any key to continue...
pause >nul
%SOGILITY_PYTHON% -m src.email_send_cli --authorize --project-root "%CD%"
if errorlevel 1 goto authorization_failed

echo.
echo SUCCESS:
echo Google email authorization completed successfully.
echo.
echo You can now close this window.
echo.
pause
exit /b 0

:missing_components
echo Google email setup could not start because required application
echo components are missing. Please contact the developer.
echo.
pause
exit /b 1

:authorization_failed
echo.
echo AUTHORIZATION NOT COMPLETED
echo.
echo Please check the message above. If the problem continues,
echo contact the developer.
echo.
pause
exit /b 1
