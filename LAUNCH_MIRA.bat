@echo off
setlocal
title MIRA Riverside Medical Centre
color 0A
cls

echo.
echo  ================================================================
echo    MIRA ^| Riverside Medical Centre ^| VoiceAI Launch
echo  ================================================================
echo.

set "P=%~dp0"
cd /d "%P%"

:: ── Pre-flight checks ─────────────────────────────────────────────────────
echo  Running pre-flight checks...
echo.

if not exist "%P%venv\Scripts\activate.bat" (
    echo  [FAIL] venv not found
    echo  Fix: py -3.13 -m venv venv then pip install -r requirements.txt
    pause & exit /b 1
)
echo  [OK] venv found

if not exist "%P%.env" (
    echo  [FAIL] .env file not found
    echo  Fix: copy .env.example .env and fill in your keys
    pause & exit /b 1
)
echo  [OK] .env found

where n8n >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] n8n not found
    echo  Fix: npm install -g n8n
    pause & exit /b 1
)
echo  [OK] n8n found

where cloudflared >nul 2>&1
if errorlevel 1 (
    echo  [FAIL] cloudflared not found
    echo  Fix: winget install --id Cloudflare.cloudflared
    pause & exit /b 1
)
echo  [OK] cloudflared found

echo.
echo  All checks passed. Launching services...
echo.
timeout /t 2 /nobreak >nul

:: ── 1. n8n ────────────────────────────────────────────────────────────────
echo  [1/3] Starting n8n...
start "n8n - Workflow Engine" cmd /k "color 0B && echo. && echo  n8n Workflow Engine - http://localhost:5678 && echo  Keep this window open && echo. && n8n start"
echo  Waiting 10s for n8n to boot...
timeout /t 10 /nobreak >nul
echo  [OK] n8n ready at http://localhost:5678

:: ── 2. Cloudflare tunnel for voice ───────────────────────────────────────
echo.
echo  [2/3] Starting Cloudflare tunnel (port 5050)...
start "Cloudflare - Voice Tunnel" cmd /k "color 0D && echo. && echo  Cloudflare Voice Tunnel (port 5050) && echo  COPY THE https://xxxx.trycloudflare.com URL && echo  Keep this window open && echo. && cloudflared tunnel --url http://localhost:5050"
timeout /t 6 /nobreak >nul
echo  [OK] Cloudflare tunnel running

:: ── 3. MIRA voice server ──────────────────────────────────────────────────
echo.
echo  [3/3] Starting MIRA voice server...
start "MIRA - Voice Server" cmd /k "color 0A && echo. && echo  MIRA Voice Server (port 5050) && echo  Keep this window open && echo. && cd /d %P% && call venv\Scripts\activate && set PYTHONPATH=%P% && python voice\twilio_server.py"
timeout /t 6 /nobreak >nul
echo  [OK] MIRA voice server launching

:: ── Done ─────────────────────────────────────────────────────────────────
cls
echo.
echo  ================================================================
echo    ALL 3 SERVICES LAUNCHED
echo  ================================================================
echo.
echo   CYAN     ^| n8n Workflow Engine   ^| localhost:5678
echo   MAGENTA  ^| Cloudflare Tunnel     ^| port 5050
echo   GREEN    ^| MIRA Voice Server     ^| port 5050
echo.
echo  ----------------------------------------------------------------
echo   BEFORE EACH SESSION - DO THESE 3 THINGS:
echo  ----------------------------------------------------------------
echo.
echo   1. MAGENTA window - Copy the Cloudflare URL:
echo      https://xxxx.trycloudflare.com
echo.
echo   2. Open .env - update this line:
echo      NGROK_VOICE_URL=https://xxxx.trycloudflare.com
echo.
echo   3. Save .env then restart the GREEN MIRA window:
echo      Ctrl+C, then: python voice\twilio_server.py
echo.
echo   4. Twilio Console - Phone Numbers - your number
echo      Voice webhook: https://xxxx.trycloudflare.com/incoming-call
echo      Method: HTTP POST - Save
echo.
echo  ----------------------------------------------------------------
echo   TEST WITHOUT A PHONE (terminal mode):
echo  ----------------------------------------------------------------
echo.
echo   Open a NEW terminal window and run:
echo   cd C:\Users\dhami\Downloads\MIRA\MIRA
echo   venv\Scripts\activate
echo   python voice\pipeline.py
echo.
echo   Test numbers:
echo   4045550001  Sarah Mitchell   confirmed    Cardiology
echo   4045550002  James Thornton   pending      Neurology
echo   4045550003  Emily Patel      rescheduled  Dermatology
echo   4045550004  Michael Walsh    cancelled    Oncology
echo   8005550010  Maria Gonzalez   confirmed    ES speaker
echo   8005550011  Carlos Mendoza   rescheduled  ES speaker
echo   9999999999  unknown patient  error path
echo.
echo  ----------------------------------------------------------------
echo   TO TEST VOICE: Call your Twilio number
echo  ----------------------------------------------------------------
echo.
echo   Press any key to open n8n dashboard...
pause >nul
start "" "http://localhost:5678"
echo.
pause
