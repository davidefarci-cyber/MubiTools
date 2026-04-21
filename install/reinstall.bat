@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM Grid — Reinstallazione / Aggiornamento forzato
REM Per uso dell'amministratore di sistema in caso di problemi.
REM Eseguire come Amministratore
REM ============================================================

set "INSTALL_DIR=C:\mubi-tools"
set "SERVICE_NAME=mubi-tools"
set "LOG_FILE=%~dp0reinstall.log"

echo.
echo ============================================================
echo   Grid — Reinstallazione
echo ============================================================
echo.
echo Log: %LOG_FILE%
echo.

REM Inizializza log
echo [%date% %time%] Reinstallazione avviata > "%LOG_FILE%"

REM Verifica privilegi
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Eseguire come Amministratore.
    pause
    exit /b 1
)
echo [%date% %time%] Privilegi amministratore OK >> "%LOG_FILE%"

if not exist "%INSTALL_DIR%\.git" (
    echo ERRORE: %INSTALL_DIR% non e' un'installazione valida.
    echo Usare install\setup.bat per una nuova installazione.
    echo [%date% %time%] ERRORE: installazione non valida >> "%LOG_FILE%"
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"

REM Leggi porta da .env
set "APP_PORT=8000"
for /f "tokens=2 delims==" %%p in ('findstr /i "^PORT=" "%INSTALL_DIR%\.env"') do set "APP_PORT=%%p"

REM Step 1: Stop servizio
echo [1/4] Stop servizio...
net stop %SERVICE_NAME% >nul 2>&1
echo   OK
echo [%date% %time%] STEP 1 OK - Servizio fermato >> "%LOG_FILE%"

REM Step 2: Git pull
echo [2/4] Aggiornamento codice (git pull)...
git pull origin main
if %errorlevel% neq 0 (
    echo   ATTENZIONE: git pull fallito. Verificare lo stato del repository.
    echo   Tentativo con git reset...
    echo [%date% %time%] WARNING: git pull fallito, tentativo reset >> "%LOG_FILE%"
    git fetch origin main
    git reset --hard origin/main
)
echo   OK
echo [%date% %time%] STEP 2 OK - Codice aggiornato >> "%LOG_FILE%"

REM Step 3: Aggiorna dipendenze
echo [3/4] Aggiornamento dipendenze...
"%INSTALL_DIR%\venv\Scripts\pip.exe" install -r requirements.txt --quiet 2>>"%LOG_FILE%"
if %errorlevel% neq 0 (
    echo   ERRORE: pip install fallito.
    echo [%date% %time%] ERRORE: pip install fallito >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo   OK
echo [%date% %time%] STEP 3 OK - Dipendenze aggiornate >> "%LOG_FILE%"

REM Step 4: Restart servizio
echo [4/4] Avvio servizio...
net start %SERVICE_NAME% >nul 2>&1

echo   Attesa risposta servizio (max 30 secondi)...
set "ATTEMPTS=0"
:wait_loop
set /a ATTEMPTS+=1
if !ATTEMPTS! gtr 15 (
    echo   ATTENZIONE: Il servizio non risponde dopo 30 secondi.
    echo   Controllare: %INSTALL_DIR%\logs\service.log
    echo [%date% %time%] WARNING: Servizio non risponde >> "%LOG_FILE%"
    goto summary
)
timeout /t 2 /nobreak >nul
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:!APP_PORT!/health' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo   OK - Servizio attivo e funzionante
    echo [%date% %time%] STEP 4 OK - Servizio attivo >> "%LOG_FILE%"
    goto summary
)
echo   Tentativo !ATTEMPTS!/15...
goto wait_loop

:summary
REM Riepilogo finale
echo.
echo ============================================================
echo   Reinstallazione completata.
echo ============================================================
echo.

REM Leggi versione
if exist "%INSTALL_DIR%\VERSION" (
    set /p "APP_VERSION=" < "%INSTALL_DIR%\VERSION"
) else (
    set "APP_VERSION=N/D"
)

REM Rileva IP del server
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "SERVER_IP=%%a"
    set "SERVER_IP=!SERVER_IP: =!"
)

echo   Versione:    !APP_VERSION!
echo   Porta:       !APP_PORT!
echo   URL locale:  http://localhost:!APP_PORT!
if defined SERVER_IP echo   URL rete:    http://!SERVER_IP!:!APP_PORT!
echo   Log servizio: %INSTALL_DIR%\logs\service.log
echo   Log reinstall: %LOG_FILE%
echo.

echo [%date% %time%] Reinstallazione completata - v!APP_VERSION! porta !APP_PORT! >> "%LOG_FILE%"
pause
