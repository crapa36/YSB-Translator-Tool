@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo  YSB Tool run launcher
echo ==========================================
echo.

set "REQ_FILE=requirements_ysik_tool.txt"
set "MAIN_FILE=main.py"

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
echo Python was not found.
echo Install Python first, and enable "Add Python to PATH".
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

if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto VENV_FAIL
)

echo [4/5] Installing and checking libraries...

call ".venv\Scripts\activate.bat"
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
    echo main.py was not found.
    echo Put this BAT in the same folder as main.py.
    pause
    exit /b 1
)

python "%MAIN_FILE%"

echo.
echo App closed.
pause
exit /b 0

:VENV_FAIL
echo.
echo Failed to create .venv.
pause
exit /b 1

:ACTIVATE_FAIL
echo.
echo Failed to activate .venv.
pause
exit /b 1

:INSTALL_FAIL
echo.
echo Failed to install libraries.
echo Try this manually:
echo .venv\Scripts\python.exe -m pip install --upgrade pip
echo .venv\Scripts\python.exe -m pip install -r %REQ_FILE%
pause
exit /b 1

:IMPORT_FAIL
echo.
echo Import test failed.
echo Try reinstalling libraries:
echo .venv\Scripts\python.exe -m pip install --upgrade --force-reinstall -r %REQ_FILE%
pause
exit /b 1
