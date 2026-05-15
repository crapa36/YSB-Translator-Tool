@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"

echo ==========================================
echo  역식붕이 툴 단일 EXE 빌드 시작
echo ==========================================

set "APP_NAME=역식붕이툴"
set "ENTRY=main.py"
set "REQ=requirements_ysik_tool.txt"
set "LOG=build_log.txt"
set "ICON_FILE=ysb_icon.ico"

set "SPLASH_FILE=ysb_splash.png"
set "BOOT_SPLASH_FILE=ysb_splash_boot.png"

echo [0/7] 기존 로그 삭제...
if exist "%LOG%" del /q "%LOG%"

if not exist "%ENTRY%" (
    echo.
    echo ❌ ENTRY 파일이 없습니다: %ENTRY%
    echo 이 BAT를 main.py가 있는 폴더에 넣고 실행하세요.
    pause
    exit /b 1
)

if not exist "%REQ%" (
    echo.
    echo ❌ requirements 파일이 없습니다: %REQ%
    echo 이 BAT를 requirements_ysik_tool.txt가 있는 폴더에 넣고 실행하세요.
    pause
    exit /b 1
)

if not exist "%ICON_FILE%" (
    echo.
    echo ❌ 아이콘 파일이 없습니다: %ICON_FILE%
    echo 이 BAT와 같은 폴더에 ysb_icon.ico를 넣어주세요.
    pause
    exit /b 1
)

if not exist "%SPLASH_FILE%" (
    echo.
    echo ❌ 스플래시 이미지 파일이 없습니다: %SPLASH_FILE%
    echo 이 BAT와 같은 폴더에 ysb_splash.png를 넣어주세요.
    pause
    exit /b 1
)

if not exist "%BOOT_SPLASH_FILE%" (
    echo.
    echo ❌ 부트 스플래시 이미지 파일이 없습니다: %BOOT_SPLASH_FILE%
    echo 이 BAT와 같은 폴더에 ysb_splash_boot.png를 넣어주세요.
    pause
    exit /b 1
)

echo [1/7] Python 확인...
py --version >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py"
) else (
    python --version >nul 2>&1
    if %errorlevel%==0 (
        set "PY_CMD=python"
    ) else (
        echo.
        echo ❌ Python이 설치되어 있지 않습니다.
        echo Python 설치 후 다시 실행하세요.
        pause
        exit /b 1
    )
)

echo [2/7] 가상환경 확인...
if not exist ".venv" (
    echo .venv 생성 중...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo ❌ 가상환경 생성 실패
        pause
        exit /b 1
    )
)

echo [3/7] 가상환경 활성화...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ❌ 가상환경 활성화 실패
    pause
    exit /b 1
)

echo [4/7] 라이브러리 설치/업데이트...
python -m pip install --upgrade pip
if errorlevel 1 goto INSTALL_FAIL

python -m pip install -r "%REQ%"
if errorlevel 1 goto INSTALL_FAIL

python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto INSTALL_FAIL

echo.
echo [5/7] 핵심 모듈 import 테스트...
python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import cv2; print('cv2 OK:', cv2.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import numpy; print('numpy OK:', numpy.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import requests, openai, replicate, PIL; print('API libs OK')"
if errorlevel 1 goto IMPORT_FAIL

echo [6/7] 이전 빌드 정리...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

echo [7/7] PyInstaller 단일 EXE 빌드 시작...
echo 단일 EXE는 실행 첫 시작이 onedir 방식보다 느릴 수 있습니다.
echo 로그 파일: %LOG%
echo.

python -m PyInstaller --noconfirm --clean --onefile --windowed --splash "%BOOT_SPLASH_FILE%" --icon "%ICON_FILE%" --add-data "%ICON_FILE%;." --add-data "%SPLASH_FILE%;." --name "%APP_NAME%" --collect-all cv2 --collect-submodules replicate --copy-metadata replicate --copy-metadata openai --copy-metadata pydantic --copy-metadata pydantic_core --copy-metadata annotated-types --copy-metadata typing-extensions --copy-metadata httpx --copy-metadata httpcore --copy-metadata anyio --copy-metadata sniffio --copy-metadata certifi --copy-metadata idna --hidden-import=cv2 --hidden-import=numpy --hidden-import=requests --hidden-import=openai --hidden-import=replicate --hidden-import=PIL "%ENTRY%" > "%LOG%" 2>&1

if errorlevel 1 (
    echo.
    echo ❌ 빌드 실패.
    if exist "%LOG%" (
        echo build_log.txt 마지막 부분:
        echo ------------------------------------------
        powershell -NoProfile -Command "Get-Content -LiteralPath '%CD%\%LOG%' -Tail 120"
        echo ------------------------------------------
    ) else (
        echo build_log.txt가 생성되지 않았습니다.
    )
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  ✅ 빌드 완료
echo  결과 위치:
echo  dist\%APP_NAME%.exe
echo ==========================================
pause
exit /b 0

:INSTALL_FAIL
echo.
echo ❌ 라이브러리 설치 실패.
pause
exit /b 1

:IMPORT_FAIL
echo.
echo ❌ 핵심 라이브러리 import 실패.
echo requirements_ysik_tool.txt 또는 설치 상태를 확인해야 합니다.
pause
exit /b 1
