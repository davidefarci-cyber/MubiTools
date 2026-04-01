@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM MUBI Tools — Setup automatico per Windows Server
REM Eseguire come Amministratore
REM ============================================================

set "APP_NAME=MUBI Tools"
set "INSTALL_DIR=C:\mubi-tools"
set "GITHUB_REPO=davidefarci-cyber/MubiTools"
set "GITHUB_URL=https://github.com/%GITHUB_REPO%.git"
set "SERVICE_NAME=mubi-tools"
set "LOG_FILE=%~dp0setup.log"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"
set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe"
set "NSSM_URL=https://nssm.cc/release/nssm-2.24.zip"
set "DEFAULT_PORT=8000"

echo.
echo ============================================================
echo   %APP_NAME% — Installazione Automatica
echo ============================================================
echo.
echo Log: %LOG_FILE%
echo.

REM Inizializza log
echo [%date% %time%] Setup avviato > "%LOG_FILE%"

REM ─── STEP 1: Verifica privilegi amministratore ───────────────
echo [STEP 1/13] Verifica privilegi amministratore...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERRORE: Questo script deve essere eseguito come Amministratore.
    echo Tasto destro sul file -^> "Esegui come amministratore"
    echo.
    pause
    exit /b 1
)
echo   OK - Privilegi amministratore confermati
echo [%date% %time%] STEP 1 OK - Admin privileges >> "%LOG_FILE%"

REM ─── STEP 2: Verifica e installazione Python ─────────────────
echo.
echo [STEP 2/13] Verifica Python 3.11+...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python non trovato. Download in corso...
    echo [%date% %time%] Python non trovato, download... >> "%LOG_FILE%"
    powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%TEMP%\python_installer.exe'" 2>>"%LOG_FILE%"
    if not exist "%TEMP%\python_installer.exe" (
        echo   ERRORE: Download Python fallito. Verificare la connessione internet.
        echo [%date% %time%] ERRORE: Download Python fallito >> "%LOG_FILE%"
        pause
        exit /b 1
    )
    echo   Installazione Python in corso (silenzioso)...
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    del "%TEMP%\python_installer.exe" 2>nul
    REM Ricarica PATH
    set "PATH=!PATH!;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
)
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERRORE: Python non disponibile dopo installazione.
    echo   Installare manualmente Python 3.11+ e aggiungerlo al PATH.
    echo [%date% %time%] ERRORE: Python non disponibile >> "%LOG_FILE%"
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo   OK - Python %PY_VER%
echo [%date% %time%] STEP 2 OK - Python %PY_VER% >> "%LOG_FILE%"

REM ─── STEP 3: Verifica e installazione Git ────────────────────
echo.
echo [STEP 3/13] Verifica Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   Git non trovato. Download in corso...
    echo [%date% %time%] Git non trovato, download... >> "%LOG_FILE%"
    powershell -Command "Invoke-WebRequest -Uri '%GIT_URL%' -OutFile '%TEMP%\git_installer.exe'" 2>>"%LOG_FILE%"
    if not exist "%TEMP%\git_installer.exe" (
        echo   ERRORE: Download Git fallito.
        echo [%date% %time%] ERRORE: Download Git fallito >> "%LOG_FILE%"
        pause
        exit /b 1
    )
    echo   Installazione Git in corso (silenzioso)...
    "%TEMP%\git_installer.exe" /VERYSILENT /NORESTART /NOCANCEL /SP-
    del "%TEMP%\git_installer.exe" 2>nul
    set "PATH=!PATH!;C:\Program Files\Git\bin"
)
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ERRORE: Git non disponibile dopo installazione.
    echo [%date% %time%] ERRORE: Git non disponibile >> "%LOG_FILE%"
    pause
    exit /b 1
)
for /f "tokens=3 delims= " %%v in ('git --version 2^>^&1') do set "GIT_VER=%%v"
echo   OK - Git %GIT_VER%
echo [%date% %time%] STEP 3 OK - Git %GIT_VER% >> "%LOG_FILE%"

REM ─── STEP 4: Clone del repository ───────────────────────────
echo.
echo [STEP 4/13] Clone repository...
if exist "%INSTALL_DIR%\.git" (
    echo   Repository esistente trovato in %INSTALL_DIR%
    echo   Aggiornamento con git pull...
    cd /d "%INSTALL_DIR%"
    git pull origin main 2>>"%LOG_FILE%"
) else (
    if exist "%INSTALL_DIR%" (
        echo   Cartella %INSTALL_DIR% esistente ma non e' un repo Git.
        set /p "CONFIRM=Sovrascrivere? [s/N]: "
        if /i not "!CONFIRM!"=="s" (
            echo   Installazione annullata.
            pause
            exit /b 1
        )
        rmdir /s /q "%INSTALL_DIR%" 2>nul
    )
    git clone "%GITHUB_URL%" "%INSTALL_DIR%" 2>>"%LOG_FILE%"
    if %errorlevel% neq 0 (
        echo   ERRORE: Clone fallito. Verificare URL repository e connessione.
        echo [%date% %time%] ERRORE: git clone fallito >> "%LOG_FILE%"
        pause
        exit /b 1
    )
)
cd /d "%INSTALL_DIR%"
echo   OK - Repository in %INSTALL_DIR%
echo [%date% %time%] STEP 4 OK - Repository clonato >> "%LOG_FILE%"

REM ─── STEP 5: Configurazione .env ────────────────────────────
echo.
echo [STEP 5/13] Configurazione ambiente...
if not exist "%INSTALL_DIR%\.env" (
    copy "%INSTALL_DIR%\.env.example" "%INSTALL_DIR%\.env" >nul

    REM Genera SECRET_KEY
    for /f %%a in ('python -c "import secrets; print(secrets.token_hex(32))"') do set "SECRET_KEY=%%a"

    REM Chiedi credenziali admin
    echo.
    set /p "ADMIN_USER=  Username admin [admin]: "
    if "!ADMIN_USER!"=="" set "ADMIN_USER=admin"

    :password_loop
    set /p "ADMIN_PASS=  Password admin (min 8 caratteri): "
    if "!ADMIN_PASS!"=="" (
        echo   Errore: la password non puo' essere vuota.
        goto password_loop
    )
    REM Verifica lunghezza minima
    set "PASS_CHECK=!ADMIN_PASS!12345678"
    if "!PASS_CHECK:~8,1!"=="" (
        echo   Errore: la password deve avere almeno 8 caratteri.
        goto password_loop
    )

    set /p "APP_PORT=  Porta servizio [%DEFAULT_PORT%]: "
    if "!APP_PORT!"=="" set "APP_PORT=%DEFAULT_PORT%"

    REM Scrivi .env
    (
        echo SECRET_KEY=!SECRET_KEY!
        echo ADMIN_USERNAME=!ADMIN_USER!
        echo ADMIN_PASSWORD=!ADMIN_PASS!
        echo DATABASE_URL=sqlite:///./database/app.db
        echo GITHUB_REPO=%GITHUB_REPO%
        echo PORT=!APP_PORT!
        echo LOG_LEVEL=INFO
        echo MAX_UPLOAD_MB=50
    ) > "%INSTALL_DIR%\.env"

    echo   OK - File .env configurato
) else (
    echo   File .env esistente, mantenuto.
    REM Leggi porta da .env
    for /f "tokens=2 delims==" %%p in ('findstr /i "^PORT=" "%INSTALL_DIR%\.env"') do set "APP_PORT=%%p"
    if "!APP_PORT!"=="" set "APP_PORT=%DEFAULT_PORT%"
)
echo [%date% %time%] STEP 5 OK - .env configurato >> "%LOG_FILE%"

REM ─── STEP 6: Creazione struttura cartelle ───────────────────
echo.
echo [STEP 6/13] Creazione cartelle...
if not exist "%INSTALL_DIR%\data\uploads" mkdir "%INSTALL_DIR%\data\uploads"
if not exist "%INSTALL_DIR%\database" mkdir "%INSTALL_DIR%\database"
if not exist "%INSTALL_DIR%\logs" mkdir "%INSTALL_DIR%\logs"
echo   OK - Cartelle create
echo [%date% %time%] STEP 6 OK - Cartelle create >> "%LOG_FILE%"

REM ─── STEP 7: Ambiente virtuale e dipendenze ─────────────────
echo.
echo [STEP 7/13] Ambiente virtuale Python e dipendenze...
if not exist "%INSTALL_DIR%\venv\Scripts\python.exe" (
    echo   Creazione virtualenv...
    python -m venv "%INSTALL_DIR%\venv"
)
echo   Installazione dipendenze...
"%INSTALL_DIR%\venv\Scripts\pip.exe" install -r "%INSTALL_DIR%\requirements.txt" --quiet 2>>"%LOG_FILE%"
if %errorlevel% neq 0 (
    echo   ERRORE: Installazione dipendenze fallita. Controllare %LOG_FILE%
    echo [%date% %time%] ERRORE: pip install fallito >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo   OK - Dipendenze installate
echo [%date% %time%] STEP 7 OK - Dipendenze installate >> "%LOG_FILE%"

REM ─── STEP 8: Download e configurazione NSSM ─────────────────
echo.
echo [STEP 8/13] Configurazione NSSM...
if not exist "%INSTALL_DIR%\install\nssm.exe" (
    echo   Download NSSM...
    powershell -Command "Invoke-WebRequest -Uri '%NSSM_URL%' -OutFile '%TEMP%\nssm.zip'" 2>>"%LOG_FILE%"
    powershell -Command "Expand-Archive -Path '%TEMP%\nssm.zip' -DestinationPath '%TEMP%\nssm_extract' -Force" 2>>"%LOG_FILE%"
    copy "%TEMP%\nssm_extract\nssm-2.24\win64\nssm.exe" "%INSTALL_DIR%\install\nssm.exe" >nul 2>>"%LOG_FILE%"
    rmdir /s /q "%TEMP%\nssm_extract" 2>nul
    del "%TEMP%\nssm.zip" 2>nul
)
if not exist "%INSTALL_DIR%\install\nssm.exe" (
    echo   ERRORE: NSSM non disponibile. Scaricare manualmente da nssm.cc
    echo [%date% %time%] ERRORE: NSSM non trovato >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo   OK - NSSM pronto
echo [%date% %time%] STEP 8 OK - NSSM configurato >> "%LOG_FILE%"

REM ─── STEP 9: Registrazione servizio Windows ─────────────────
echo.
echo [STEP 9/13] Registrazione servizio Windows...
REM Rimuovi servizio esistente
"%INSTALL_DIR%\install\nssm.exe" stop %SERVICE_NAME% >nul 2>&1
"%INSTALL_DIR%\install\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1

REM Registra nuovo servizio
"%INSTALL_DIR%\install\nssm.exe" install %SERVICE_NAME% "%INSTALL_DIR%\venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port !APP_PORT!"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% Description "MUBI Tools - Gestione incassi"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppStdout "%INSTALL_DIR%\logs\service.log"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppStderr "%INSTALL_DIR%\logs\service.log"
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppRotateFiles 1
"%INSTALL_DIR%\install\nssm.exe" set %SERVICE_NAME% AppRotateBytes 5242880

echo   OK - Servizio '%SERVICE_NAME%' registrato
echo [%date% %time%] STEP 9 OK - Servizio registrato >> "%LOG_FILE%"

REM ─── STEP 10: Regola firewall ───────────────────────────────
echo.
echo [STEP 10/13] Configurazione firewall...
netsh advfirewall firewall delete rule name="MUBI Tools Web App" >nul 2>&1
netsh advfirewall firewall add rule name="MUBI Tools Web App" dir=in action=allow protocol=TCP localport=!APP_PORT! >nul 2>&1
echo   OK - Porta !APP_PORT! aperta nel firewall
echo [%date% %time%] STEP 10 OK - Firewall porta !APP_PORT! >> "%LOG_FILE%"

REM ─── STEP 11: Avvio e verifica ──────────────────────────────
echo.
echo [STEP 11/13] Avvio servizio...
net start %SERVICE_NAME% >nul 2>&1

echo   Attesa risposta servizio (max 30 secondi)...
set "ATTEMPTS=0"
:wait_loop
set /a ATTEMPTS+=1
if !ATTEMPTS! gtr 15 (
    echo   ATTENZIONE: Il servizio non risponde dopo 30 secondi.
    echo   Controllare: %INSTALL_DIR%\logs\service.log
    echo [%date% %time%] WARNING: Servizio non risponde >> "%LOG_FILE%"
    goto step12
)
timeout /t 2 /nobreak >nul
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:!APP_PORT!/health' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo   OK - Servizio attivo e funzionante
    echo [%date% %time%] STEP 11 OK - Servizio attivo >> "%LOG_FILE%"
    goto step12
)
echo   Tentativo !ATTEMPTS!/15...
goto wait_loop

:step12
REM ─── STEP 12: Primo avvio database ──────────────────────────
echo.
echo [STEP 12/13] Database...
echo   Il database e l'utente admin vengono creati automaticamente al primo avvio.
echo [%date% %time%] STEP 12 OK - Database auto-init >> "%LOG_FILE%"

REM ─── STEP 13: Riepilogo finale ──────────────────────────────
echo.
echo ============================================================
echo   INSTALLAZIONE COMPLETATA CON SUCCESSO
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
echo   Admin user:  !ADMIN_USER!
echo   Log servizio: %INSTALL_DIR%\logs\service.log
echo   Log setup:    %LOG_FILE%
echo.

echo [%date% %time%] Setup completato - v!APP_VERSION! porta !APP_PORT! >> "%LOG_FILE%"

REM Apri browser
start "" "http://localhost:!APP_PORT!"

echo   Il browser si e' aperto sulla pagina di login.
echo   Premere un tasto per chiudere questa finestra.
pause >nul
