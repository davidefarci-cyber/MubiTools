@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM MUBI Tools — Registrazione servizio Windows con NSSM
REM Questo script puo' essere eseguito separatamente per
REM ri-registrare il servizio senza reinstallare tutto.
REM Eseguire come Amministratore.
REM ============================================================

set "INSTALL_DIR=C:\mubi-tools"
set "SERVICE_NAME=mubi-tools"

REM Verifica privilegi
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Eseguire come Amministratore.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\install\nssm.exe" (
    echo ERRORE: NSSM non trovato in %INSTALL_DIR%\install\nssm.exe
    echo Eseguire prima install\setup.bat
    pause
    exit /b 1
)

REM Leggi porta
set "APP_PORT=8000"
if exist "%INSTALL_DIR%\.env" (
    for /f "tokens=2 delims==" %%p in ('findstr /i "^PORT=" "%INSTALL_DIR%\.env"') do set "APP_PORT=%%p"
)

echo.
echo MUBI Tools — Registrazione servizio
echo Porta: !APP_PORT!
echo.

REM Stop e rimuovi esistente
echo Rimozione servizio esistente...
"%INSTALL_DIR%\install\nssm.exe" stop %SERVICE_NAME% >nul 2>&1
"%INSTALL_DIR%\install\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1
timeout /t 2 /nobreak >nul

REM Registra
echo Registrazione nuovo servizio...
"%INSTALL_DIR%\install\nssm.exe" install %SERVICE_NAME% "%INSTALL_DIR%\venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port !APP_PORT!"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% Description "MUBI Tools - Gestione incassi"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppStdout "%INSTALL_DIR%\logs\service.log"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppStderr "%INSTALL_DIR%\logs\service.log"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppRotateFiles 1
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppRotateBytes 5242880

REM Avvia
echo Avvio servizio...
net start %SERVICE_NAME%

echo.
echo Servizio '%SERVICE_NAME%' registrato e avviato su porta !APP_PORT!.
echo.
pause
