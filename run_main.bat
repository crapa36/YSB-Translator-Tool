@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo  역식붕이 툴 실행 준비
echo ==========================================

set REQ_FILE=requirements_ysik_tool.txt
set MAIN_FILE=main.py

REM ------------------------------------------
REM 1. Python 확인
REM ------------------------------------------
echo [1/5] Python 설치 확인 중...

py --version >nul 2>&1
if %errorlevel%==0 (
    set PY_CMD=py
    goto PY_FOUND
)

python --version >nul 2>&1
if %errorlevel%==0 (
    set PY_CMD=python
    goto PY_FOUND
)

echo.
echo ❌ Python이 설치되어 있지 않습니다.
echo Python을 먼저 설치해야 합니다.
echo 설치 시 "Add Python to PATH"를 꼭 체크하세요.
echo.
pause
exit /b 1

:PY_FOUND
echo Python 확인 완료: %PY_CMD%

REM ------------------------------------------
REM 2. requirements 파일 자동 생성
REM ------------------------------------------
echo [2/5] 라이브러리 목록 확인 중...

if not exist "%REQ_FILE%" (
    echo requirements 파일이 없어 새로 생성합니다.

    > "%REQ_FILE%" echo PyQt6
    >> "%REQ_FILE%" echo opencv-python
    >> "%REQ_FILE%" echo numpy
    >> "%REQ_FILE%" echo requests
    >> "%REQ_FILE%" echo openai
    >> "%REQ_FILE%" echo pillow
    >> "%REQ_FILE%" echo replicate
)

REM ------------------------------------------
REM 3. 가상환경 생성
REM ------------------------------------------
echo [3/5] 가상환경 확인 중...

if not exist ".venv" (
    echo .venv 가상환경 생성 중...
    %PY_CMD% -m venv .venv

    if errorlevel 1 (
        echo.
        echo ❌ 가상환경 생성 실패
        pause
        exit /b 1
    )
)

REM ------------------------------------------
REM 4. 라이브러리 설치 / 확인
REM ------------------------------------------
echo [4/5] 라이브러리 설치 및 확인 중...

call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip
python -m pip install -r "%REQ_FILE%"

echo.
echo 핵심 라이브러리 import 테스트 중...

python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto LIB_FAIL

python -c "import cv2; print('opencv-python OK:', cv2.__version__)"
if errorlevel 1 goto LIB_FAIL

python -c "import numpy; print('numpy OK:', numpy.__version__)"
if errorlevel 1 goto LIB_FAIL

python -c "import requests; print('requests OK')"
if errorlevel 1 goto LIB_FAIL

python -c "import openai; print('openai OK')"
if errorlevel 1 goto LIB_FAIL

python -c "import PIL; print('pillow OK')"
if errorlevel 1 goto LIB_FAIL

python -c "import replicate; print('replicate OK')"
if errorlevel 1 goto LIB_FAIL

REM ------------------------------------------
REM 5. 프로그램 실행
REM ------------------------------------------
echo.
echo [5/5] 프로그램 실행 중...

if not exist "%MAIN_FILE%" (
    echo.
    echo ❌ main.py를 찾을 수 없습니다.
    echo 이 BAT 파일을 main.py가 있는 폴더에 넣어주세요.
    pause
    exit /b 1
)

python "%MAIN_FILE%"

echo.
echo 프로그램이 종료되었습니다.
pause
exit /b 0

:LIB_FAIL
echo.
echo ❌ 라이브러리 import 테스트 실패
echo 설치가 제대로 되지 않았습니다.
echo 아래 명령으로 수동 재설치를 시도해볼 수 있습니다:
echo.
echo .venv\Scripts\activate
echo python -m pip install --upgrade --force-reinstall -r %REQ_FILE%
echo.
pause
exit /b 1