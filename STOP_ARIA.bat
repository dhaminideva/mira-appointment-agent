@echo off
title ARIA — Stop All Services
color 0C
echo.
echo  Stopping all ARIA services...
echo.
taskkill /f /fi "WINDOWTITLE eq n8n - Workflow Engine" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq ngrok - n8n Tunnel" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Cloudflare - Voice Tunnel" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq ARIA - Voice Server" >nul 2>&1
taskkill /f /im "node.exe" /fi "WINDOWTITLE eq n8n*" >nul 2>&1
taskkill /f /im "ngrok.exe" >nul 2>&1
taskkill /f /im "cloudflared.exe" >nul 2>&1
echo  All services stopped.
echo.
echo  To restart everything: double-click LAUNCH_ARIA.bat
echo.
pause
