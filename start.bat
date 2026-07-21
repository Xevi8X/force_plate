@echo off
setlocal
cd /d "%~dp0"

python3 "%~dp0start.py"
exit /b %ERRORLEVEL%
