@echo off
title ARIA Status Check
cd /d "%~dp0"
call venv\Scripts\activate >nul 2>&1
python check_status_helper.py
pause
