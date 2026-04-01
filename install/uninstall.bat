@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM MUBI Tools — Disinstallazione
REM Eseguire come Amministratore
REM ============================================================

set "INSTALL_DIR=C:\mubi-tools"
set "SERVICE_NAME=mubi-tools"

echo.
echo ============================================================
echo   MUBI Tools — Disinstallazione
echo ============================================================
echo.

REM Verifica privilegi
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Eseguire come Amministratore.
    pause
    exit /b 1
)

REM Step 1: Stop servizio
echo [1/5] Stop servizio...
net stop %SERVICE_NAME% >nul 2>&1
echo   OK

REM Step 2: Rimuovi servizio NSSM
echo [2/5] Rimozione servizio...
if exist "%INSTALL_DIR%\install\nssm.exe" (
    "%INSTALL_DIR%\install\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1
) else (
    sc delete %SERVICE_NAME% >nul 2>&1
)
echo   OK

REM Step 3: Rimuovi regola firewall
echo [3/5] Rimozione regola firewall...
netsh advfirewall firewall delete rule name="MUBI Tools Web App" >nul 2>&1
echo   OK

REM Step 4: Chiedi conferma per dati
echo.
echo [4/5] Eliminazione dati...
set /p "DEL_DATA=Eliminare database e file caricati? [s/N]: "
if /i "!DEL_DATA!"=="s" (
    if exist "%INSTALL_DIR%\database" rmdir /s /q "%INSTALL_DIR%\database"
    if exist "%INSTALL_DIR%\data\uploads" rmdir /s /q "%INSTALL_DIR%\data\uploads"
    echo   Dati eliminati
) else (
    echo   Dati mantenuti
)

REM Step 5: Chiedi conferma per cartella completa
echo.
echo [5/5] Eliminazione cartella installazione...
set /p "DEL_ALL=Eliminare TUTTA la cartella %INSTALL_DIR%? [s/N]: "
if /i "!DEL_ALL!"=="s" (
    cd /d "%USERPROFILE%"
    rmdir /s /q "%INSTALL_DIR%" 2>nul
    echo   Cartella eliminata
) else (
    echo   Cartella mantenuta
)

echo.
echo ============================================================
echo   Disinstallazione completata.
echo ============================================================
echo.
pause
