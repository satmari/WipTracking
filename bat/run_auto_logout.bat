@echo off
setlocal enabledelayedexpansion

REM =======================
REM   CONFIG
REM =======================
set APP_DIR=D:\DjangoApps\WipTracking
set BAT_DIR=D:\DjangoApps\WipTracking\bat
set LOG_FILE=%BAT_DIR%\auto_logout.log

REM 10 MB (10 * 1024 * 1024)
set MAX_SIZE=10485760

set VENV_ACT=%APP_DIR%\.venv\Scripts\activate.bat
set PYTHON_EXE=%APP_DIR%\.venv\Scripts\python.exe

REM =======================
REM  CHANGE DIR
REM =======================
cd /d "%APP_DIR%"

REM =======================
REM  LOG ROTATION
REM =======================
set SIZE=

if exist "%LOG_FILE%" (
    for %%F in ("%LOG_FILE%") do set SIZE=%%~zF
)

REM Ako postoji SIZE i veci je od MAX_SIZE -> rotiraj
if defined SIZE (
    if %SIZE% GTR %MAX_SIZE% (
        echo Log exceeds 10MB, rotating...

        set INDEX=1
        :findFreeLog
        if exist "%BAT_DIR%\auto_logout_!INDEX!.log" (
            set /a INDEX+=1
            goto findFreeLog
        )

        move "%LOG_FILE%" "%BAT_DIR%\auto_logout_!INDEX!.log" >nul
        echo Rotated to auto_logout_!INDEX!.log
    )
)

REM =======================
REM HEADER IN MAIN LOG
REM =======================
echo. >> "%LOG_FILE%"
echo [%date% %time%] --- Auto logout task started --- >> "%LOG_FILE%"

REM =======================
REM ACTIVATE VENV
REM =======================
call "%VENV_ACT%" >> "%LOG_FILE%" 2>&1

REM =======================
REM RUN DJANGO COMMAND
REM =======================
"%PYTHON_EXE%" manage.py auto_logout_operators >> "%LOG_FILE%" 2>&1

echo [%date% %time%] --- Auto logout task finished --- >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
