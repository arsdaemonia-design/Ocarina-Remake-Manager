@echo off
setlocal
set "APP_DIR=%~dp0"
set "EXE_PATH=%APP_DIR%OcarinaRemakeManager.exe"

if exist "%EXE_PATH%" (
    start "" /D "%APP_DIR%" "%EXE_PATH%"
    exit /b 0
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" /D "%APP_DIR%" pyw -3 "%APP_DIR%app.py"
    exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    cd /d "%APP_DIR%"
    py -3 "%APP_DIR%app.py"
    exit /b %errorlevel%
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" /D "%APP_DIR%" pythonw "%APP_DIR%app.py"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    cd /d "%APP_DIR%"
    python "%APP_DIR%app.py"
    exit /b %errorlevel%
)

echo No se encontro OcarinaRemakeManager.exe ni Python 3.
echo Could not find OcarinaRemakeManager.exe or Python 3.
pause
exit /b 1
