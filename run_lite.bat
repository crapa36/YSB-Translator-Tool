@echo off
set PIP_DISABLE_PIP_VERSION_CHECK=1
set PIP_NO_PYTHON_VERSION_WARNING=1
set PIP_NO_INPUT=1
setlocal EnableExtensions EnableDelayedExpansion

REM ==========================================================
REM  YSB Tool Lite - Source Run Launcher
REM  - Uses the shared .venv in the project root
REM  - Runs API/Lite entry point: main_lite.py
REM ==========================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "APP_ROOT="
if exist "main_lite.py" if exist "ysb\__init__.py" set "APP_ROOT=%CD%"
if not defined APP_ROOT (
    if exist "..\main_lite.py" if exist "..\ysb\__init__.py" (
        cd /d ".."
        set "APP_ROOT=%CD%"
    )
)
if not defined APP_ROOT (
    echo.
    echo [ERROR] Project root was not found.
    echo Put this BAT in the project root folder, next to main_lite.py and the ysb folder.
    echo.
    pause
    exit /b 1
)

cd /d "%APP_ROOT%"

set "VENV_DIR=%APP_ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACT=%VENV_DIR%\Scripts\activate.bat"
set "PYTHONUTF8=1"
set "PYTHONPATH=%APP_ROOT%;%PYTHONPATH%"
set "YSB_TOOL_EDITION=lite"

echo ==========================================
for /f "usebackq delims=" %%V in (`python -c "from ysb.version_info import APP_VERSION; print(APP_VERSION)" 2^>nul`) do set "YSB_APP_VERSION=%%V"
if not defined YSB_APP_VERSION set "YSB_APP_VERSION=current"
echo  YSB Tool Lite %YSB_APP_VERSION% - Run Source
echo ==========================================
echo Project root: %APP_ROOT%
echo Virtual env : %VENV_DIR%
echo.

py --version >nul 2>nul
if "%errorlevel%"=="0" (
    set "PY_CMD=py"
    goto PY_FOUND
)
python --version >nul 2>nul
if "%errorlevel%"=="0" (
    set "PY_CMD=python"
    goto PY_FOUND
)
echo [ERROR] Python was not found.
pause
exit /b 1

:PY_FOUND
if not exist "%VENV_PY%" (
    echo Creating shared virtual environment...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto VENV_FAIL
)

call "%VENV_ACT%"
if errorlevel 1 goto ACTIVATE_FAIL

python -m pip --disable-pip-version-check install --upgrade pip
if errorlevel 1 goto INSTALL_FAIL
if exist "requirements\common.txt" python -m pip --disable-pip-version-check install -r "requirements\common.txt"
if errorlevel 1 goto INSTALL_FAIL
if exist "requirements\lite.txt" python -m pip --disable-pip-version-check install -r "requirements\lite.txt"
if errorlevel 1 goto INSTALL_FAIL

python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto IMPORT_FAIL

echo.
echo Starting YSB Tool Lite...
python "main_lite.py" %*
exit /b %errorlevel%

:VENV_FAIL
echo [ERROR] Failed to create virtual environment.
pause
exit /b 1
:ACTIVATE_FAIL
echo [ERROR] Failed to activate virtual environment.
pause
exit /b 1
:INSTALL_FAIL
echo [ERROR] Failed to install libraries.
pause
exit /b 1
:IMPORT_FAIL
echo [ERROR] Import test failed.
pause
exit /b 1
