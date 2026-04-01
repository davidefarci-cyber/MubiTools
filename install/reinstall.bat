@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM MUBI Tools — Reinstallazione / Aggiornamento forzato
REM Per uso dell'amministratore di sistema in caso di problemi.
REM Eseguire come Amministratore
REM ============================================================

set "INSTALL_DIR=C:\mubi-tools"
set "SERVICE_NAME=mubi-tools"

echo.
echo ============================================================
echo   MUBI Tools — Reinstallazione
echo ============================================================
echo.

REM Verifica privilegi
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Eseguire come Amministratore.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\.git" (
    echo ERRORE: %INSTALL_DIR% non e' un'installazione valida.
    echo Usare install\setup.bat per una nuova installazione.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"

REM Step 1: Stop servizio
echo [1/4] Stop servizio...
net stop %SERVICE_NAME% >nul 2>&1
echo   OK

REM Step 2: Git pull
echo [2/4] Aggiornamento codice (git pull)...
git pull origin main
if %errorlevel% neq 0 (
    echo   ATTENZIONE: git pull fallito. Verificare lo stato del repository.
    echo   Tentativo con git reset...
    git fetch origin main
    git reset --hard origin/main
)
echo   OK

REM Step 3: Aggiorna dipendenze
echo [3/4] Aggiornamento dipendenze...
"%INSTALL_DIR%\venv\Scripts\pip.exe" install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo   ERRORE: pip install fallito.
    pause
    exit /b 1
)
echo   OK

REM Step 4: Restart servizio
echo [4/4] Avvio servizio...
net start %SERVICE_NAME%
if %errorlevel% neq 0 (
    echo   ERRORE: Avvio servizio fallito. Controllare logs\service.log
    pause
    exit /b 1
)

REM Attendi e verifica
echo   Attesa risposta...
timeout /t 5 /nobreak >nul

REM Leggi porta da .env
set "APP_PORT=8000"
for /f "tokens=2 delims==" %%p in ('findstr /i "^PORT=" "%INSTALL_DIR%\.env"') do set "APP_PORT=%%p"

powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:!APP_PORT!/health' -UseBasicParsing -TimeoutSec 5; Write-Host $r.Content } catch { Write-Host 'ERRORE: Servizio non risponde' }"

echo.
echo ============================================================
echo   Reinstallazione completata.
echo ============================================================
echo.
pause
