@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM Grid — Disinstallazione
REM Eseguire come Amministratore
REM ============================================================

set "INSTALL_DIR=C:\mubi-tools"
set "SERVICE_NAME=mubi-tools"
set "LOG_FILE=%~dp0uninstall.log"

echo.
echo ============================================================
echo   Grid — Disinstallazione
echo ============================================================
echo.
echo Log: %LOG_FILE%
echo.

REM Inizializza log
echo [%date% %time%] Disinstallazione avviata > "%LOG_FILE%"

REM Verifica privilegi
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Eseguire come Amministratore.
    pause
    exit /b 1
)
echo [%date% %time%] Privilegi amministratore OK >> "%LOG_FILE%"

REM Step 1: Stop servizio
echo [1/5] Stop servizio...
net stop %SERVICE_NAME% >nul 2>&1
echo   OK
echo [%date% %time%] STEP 1 OK - Servizio fermato >> "%LOG_FILE%"

REM Step 2: Rimuovi servizio NSSM
echo [2/5] Rimozione servizio...
if exist "%INSTALL_DIR%\install\nssm.exe" (
    "%INSTALL_DIR%\install\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1
) else (
    sc delete %SERVICE_NAME% >nul 2>&1
)
echo   OK
echo [%date% %time%] STEP 2 OK - Servizio rimosso >> "%LOG_FILE%"

REM Step 3: Rimuovi regola firewall
echo [3/5] Rimozione regola firewall...
netsh advfirewall firewall delete rule name="MUBI Tools Web App" >nul 2>&1
netsh advfirewall firewall delete rule name="Grid Web App" >nul 2>&1
echo   OK
echo [%date% %time%] STEP 3 OK - Regola firewall rimossa >> "%LOG_FILE%"

REM Step 4: Chiedi conferma per dati
echo.
echo [4/5] Eliminazione dati...
set /p "DEL_DATA=Eliminare database e file caricati? [s/N]: "
if /i "!DEL_DATA!"=="s" (
    if exist "%INSTALL_DIR%\database" rmdir /s /q "%INSTALL_DIR%\database"
    if exist "%INSTALL_DIR%\data\uploads" rmdir /s /q "%INSTALL_DIR%\data\uploads"
    echo   Dati eliminati
    echo [%date% %time%] STEP 4 - Dati eliminati >> "%LOG_FILE%"
) else (
    echo   Dati mantenuti
    echo [%date% %time%] STEP 4 - Dati mantenuti >> "%LOG_FILE%"
)

REM Step 5: Chiedi conferma per cartella completa
echo.
echo [5/5] Eliminazione cartella installazione...
set /p "DEL_ALL=Eliminare TUTTA la cartella %INSTALL_DIR%? [s/N]: "
if /i "!DEL_ALL!"=="s" (
    cd /d "%USERPROFILE%"
    rmdir /s /q "%INSTALL_DIR%" 2>nul
    echo   Cartella eliminata
    echo [%date% %time%] STEP 5 - Cartella eliminata >> "%LOG_FILE%"
) else (
    echo   Cartella mantenuta
    echo [%date% %time%] STEP 5 - Cartella mantenuta >> "%LOG_FILE%"
)

echo.
echo ============================================================
echo   Disinstallazione completata.
echo ============================================================
echo.
echo [%date% %time%] Disinstallazione completata >> "%LOG_FILE%"
pause
