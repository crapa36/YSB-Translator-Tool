@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==========================================================
REM  YSB Translator Tool v2.0.0 - Source Run Launcher
REM  - Creates/uses the virtual environment in the project root
REM  - Works from project root or from a one-level subfolder
REM ==========================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Find project root.
REM Preferred: the folder where main.py and ysb\ exist.
set "APP_ROOT="
if exist "main.py" if exist "ysb\__init__.py" set "APP_ROOT=%CD%"

if not defined APP_ROOT (
    if exist "..\main.py" if exist "..\ysb\__init__.py" (
        cd /d ".."
        set "APP_ROOT=%CD%"
    )
)

if not defined APP_ROOT (
    echo.
    echo [ERROR] Project root was not found.
    echo Put this BAT in the project root folder, next to main.py and the ysb folder.
    echo Or put it in a one-level subfolder under the project root.
    echo.
    pause
    exit /b 1
)

cd /d "%APP_ROOT%"

set "REQ_FILE=requirements_ysik_tool.txt"
set "MAIN_FILE=main.py"
set "VENV_DIR=%APP_ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACT=%VENV_DIR%\Scripts\activate.bat"

set "PYTHONUTF8=1"
set "PYTHONPATH=%APP_ROOT%;%PYTHONPATH%"

echo ==========================================
echo  YSB Translator Tool v2.0.0 - Run Source
echo ==========================================
echo Project root: %APP_ROOT%
echo Virtual env : %VENV_DIR%
echo.

echo [1/5] Checking Python...

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

echo.
echo [ERROR] Python was not found.
echo Install Python first, and enable "Add Python to PATH".
echo.
pause
exit /b 1

:PY_FOUND
echo Python command: %PY_CMD%
echo.

echo [2/5] Checking requirements file...

if not exist "%REQ_FILE%" (
    echo Creating %REQ_FILE%...
    (
        echo PyQt6
        echo opencv-python
        echo numpy
        echo requests
        echo openai
        echo pillow
        echo replicate
        echo google-auth
        echo google-auth-oauthlib
        echo google-api-python-client
    ) > "%REQ_FILE%"
)

echo [3/5] Checking virtual environment...

if not exist "%VENV_PY%" (
    echo Creating virtual environment in project root...
    echo %VENV_DIR%
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 goto VENV_FAIL
)

echo [4/5] Installing and checking libraries...

call "%VENV_ACT%"
if errorlevel 1 goto ACTIVATE_FAIL

python -m pip install --upgrade pip
if errorlevel 1 goto INSTALL_FAIL

python -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto INSTALL_FAIL

echo.
echo Import test...

python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import cv2; print('opencv-python OK:', cv2.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import numpy; print('numpy OK:', numpy.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import requests; print('requests OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import openai; print('openai OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import PIL; print('pillow OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import replicate; print('replicate OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import google_auth_oauthlib; print('google-auth-oauthlib OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import google.oauth2.credentials; import google.auth.transport.requests; print('google-auth OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import googleapiclient.discovery; print('google-api-python-client OK')"
if errorlevel 1 goto IMPORT_FAIL

echo.
echo [5/5] Running app...

if not exist "%MAIN_FILE%" (
    echo.
    echo [ERROR] main.py was not found in project root.
    echo Current folder: %CD%
    echo.
    pause
    exit /b 1
)

python "%MAIN_FILE%" %*

echo.
echo App closed.
pause
exit /b 0

:VENV_FAIL
echo.
echo [ERROR] Failed to create virtual environment.
echo Target: %VENV_DIR%
echo.
pause
exit /b 1

:ACTIVATE_FAIL
echo.
echo [ERROR] Failed to activate virtual environment.
echo Target: %VENV_ACT%
echo.
pause
exit /b 1

:INSTALL_FAIL
echo.
echo [ERROR] Failed to install libraries.
echo Try this manually:
echo "%VENV_PY%" -m pip install --upgrade pip
echo "%VENV_PY%" -m pip install -r "%REQ_FILE%"
echo.
pause
exit /b 1

:IMPORT_FAIL
echo.
echo [ERROR] Import test failed.
echo Try reinstalling libraries:
echo "%VENV_PY%" -m pip install --upgrade --force-reinstall -r "%REQ_FILE%"
echo.
pause
exit /b 1
