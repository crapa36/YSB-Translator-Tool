@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title YSB Tool EXE Build

rem ==========================================================
rem YSB Tool onefile build BAT
rem ASCII-safe BAT. Output EXE name can be renamed after build.
rem ==========================================================

set "APP_NAME=YSB_Tool_v1.8.0"
set "USE_BOOT_SPLASH=0"

set "ENTRY=main.py"
set "REQ=requirements_ysik_tool.txt"
set "LOG=build_log.txt"
set "ICON_FILE=ysb_icon.ico"
set "SPLASH_FILE=ysb_splash.png"
set "BOOT_SPLASH_FILE=ysb_splash_boot.png"

echo ==========================================
echo  YSB Tool onefile EXE build
echo ==========================================
echo.
echo APP_NAME=%APP_NAME%
echo USE_BOOT_SPLASH=%USE_BOOT_SPLASH%
echo.

if exist "%LOG%" del /q "%LOG%" >nul 2>nul

if not exist "%ENTRY%" goto MISSING_ENTRY
if not exist "%REQ%" goto MISSING_REQ
if not exist "%ICON_FILE%" goto MISSING_ICON
if not exist "%SPLASH_FILE%" goto MISSING_QT_SPLASH

if "%USE_BOOT_SPLASH%"=="1" (
    if not exist "%BOOT_SPLASH_FILE%" goto MISSING_BOOT_SPLASH
    echo Boot splash: ON
) else (
    echo Boot splash: OFF
)
echo.

echo [1/7] Checking Python...
py --version >nul 2>nul
if "%errorlevel%"=="0" (
    set "PY_CMD=py"
) else (
    python --version >nul 2>nul
    if "%errorlevel%"=="0" (
        set "PY_CMD=python"
    ) else (
        goto NO_PYTHON
    )
)

echo Python command: %PY_CMD%
echo.

echo [2/7] Checking virtual environment...
if not exist ".venv\Scripts\python.exe" (
    echo Creating .venv...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto VENV_FAIL
)

echo [3/7] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto ACTIVATE_FAIL

echo [4/7] Installing/updating libraries...
python -m pip install --upgrade pip
if errorlevel 1 goto INSTALL_FAIL

python -m pip install -r "%REQ%"
if errorlevel 1 goto INSTALL_FAIL

python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto INSTALL_FAIL

echo.
echo [5/7] Import test...

python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import cv2; print('cv2 OK:', cv2.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import numpy; print('numpy OK:', numpy.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import requests, openai, replicate, PIL; print('API libs OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import google_auth_oauthlib; import google.oauth2.credentials; import google.auth.transport.requests; import googleapiclient.discovery; print('Google cloud libs OK')"
if errorlevel 1 goto IMPORT_FAIL

echo.
echo [6/7] Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo.
echo [7/7] Building onefile EXE...
echo Build log: %LOG%
echo.

if "%USE_BOOT_SPLASH%"=="1" goto BUILD_WITH_BOOT_SPLASH
goto BUILD_NO_BOOT_SPLASH

:BUILD_NO_BOOT_SPLASH
python -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --icon "%ICON_FILE%" ^
 --add-data "%ICON_FILE%;." ^
 --add-data "%SPLASH_FILE%;." ^
 --name "%APP_NAME%" ^
 --collect-all cv2 ^
 --collect-submodules replicate ^
 --copy-metadata replicate ^
 --copy-metadata openai ^
 --copy-metadata pydantic ^
 --copy-metadata pydantic_core ^
 --copy-metadata annotated-types ^
 --copy-metadata typing-extensions ^
 --copy-metadata httpx ^
 --copy-metadata httpcore ^
 --copy-metadata anyio ^
 --copy-metadata sniffio ^
 --copy-metadata certifi ^
 --copy-metadata idna ^
 --hidden-import=cv2 ^
 --hidden-import=numpy ^
 --hidden-import=requests ^
 --hidden-import=openai ^
 --hidden-import=replicate ^
 --hidden-import=PIL ^
 --collect-all googleapiclient ^
 --collect-submodules google ^
 --collect-submodules google_auth_oauthlib ^
 --copy-metadata google-auth ^
 --copy-metadata google-auth-oauthlib ^
 --copy-metadata google-api-python-client ^
 --copy-metadata google-auth-httplib2 ^
 --copy-metadata httplib2 ^
 --copy-metadata uritemplate ^
 --hidden-import=google_auth_oauthlib.flow ^
 --hidden-import=google.oauth2.credentials ^
 --hidden-import=google.auth.transport.requests ^
 --hidden-import=googleapiclient.discovery ^
 "%ENTRY%" > "%LOG%" 2>&1
goto CHECK_BUILD_RESULT

:BUILD_WITH_BOOT_SPLASH
python -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --splash "%BOOT_SPLASH_FILE%" ^
 --icon "%ICON_FILE%" ^
 --add-data "%ICON_FILE%;." ^
 --add-data "%SPLASH_FILE%;." ^
 --add-data "%BOOT_SPLASH_FILE%;." ^
 --name "%APP_NAME%" ^
 --collect-all cv2 ^
 --collect-submodules replicate ^
 --copy-metadata replicate ^
 --copy-metadata openai ^
 --copy-metadata pydantic ^
 --copy-metadata pydantic_core ^
 --copy-metadata annotated-types ^
 --copy-metadata typing-extensions ^
 --copy-metadata httpx ^
 --copy-metadata httpcore ^
 --copy-metadata anyio ^
 --copy-metadata sniffio ^
 --copy-metadata certifi ^
 --copy-metadata idna ^
 --hidden-import=cv2 ^
 --hidden-import=numpy ^
 --hidden-import=requests ^
 --hidden-import=openai ^
 --hidden-import=replicate ^
 --hidden-import=PIL ^
 --collect-all googleapiclient ^
 --collect-submodules google ^
 --collect-submodules google_auth_oauthlib ^
 --copy-metadata google-auth ^
 --copy-metadata google-auth-oauthlib ^
 --copy-metadata google-api-python-client ^
 --copy-metadata google-auth-httplib2 ^
 --copy-metadata httplib2 ^
 --copy-metadata uritemplate ^
 --hidden-import=google_auth_oauthlib.flow ^
 --hidden-import=google.oauth2.credentials ^
 --hidden-import=google.auth.transport.requests ^
 --hidden-import=googleapiclient.discovery ^
 "%ENTRY%" > "%LOG%" 2>&1
goto CHECK_BUILD_RESULT

:CHECK_BUILD_RESULT
if errorlevel 1 goto BUILD_FAIL

echo.
echo ==========================================
echo  Build complete
echo  Output:
echo  dist\%APP_NAME%.exe
echo ==========================================
pause
exit /b 0

:MISSING_ENTRY
echo.
echo Missing file: %ENTRY%
echo Put this BAT in the same folder as main.py.
pause
exit /b 1

:MISSING_REQ
echo.
echo Missing file: %REQ%
pause
exit /b 1

:MISSING_ICON
echo.
echo Missing file: %ICON_FILE%
pause
exit /b 1

:MISSING_QT_SPLASH
echo.
echo Missing file: %SPLASH_FILE%
pause
exit /b 1

:MISSING_BOOT_SPLASH
echo.
echo Missing boot splash file: %BOOT_SPLASH_FILE%
pause
exit /b 1

:NO_PYTHON
echo.
echo Python was not found.
echo Install Python first, and enable "Add Python to PATH".
pause
exit /b 1

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
echo Library installation failed.
pause
exit /b 1

:IMPORT_FAIL
echo.
echo Import test failed.
pause
exit /b 1

:BUILD_FAIL
echo.
echo Build failed.
echo Check %LOG%.
pause
exit /b 1
