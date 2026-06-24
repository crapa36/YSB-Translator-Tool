@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM ==========================================================
REM  YSB Tool Local - Source Run Launcher
REM  - Uses the shared .venv in the project root
REM  - Runs Local entry point: main_local.py
REM  - Does NOT reinstall packages every run. Use setup BAT for venv setup.
REM  - Keeps the console open on crash so the error is readable.
REM ==========================================================

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "APP_ROOT="
if exist "main_local.py" if exist "ysb\__init__.py" set "APP_ROOT=%CD%"
if not defined APP_ROOT (
    if exist "..\main_local.py" if exist "..\ysb\__init__.py" (
        cd /d ".."
        set "APP_ROOT=%CD%"
    )
)
if not defined APP_ROOT (
    echo.
    echo [ERROR] Project root was not found.
    echo Put this BAT in the project root folder, next to main_local.py and the ysb folder.
    echo.
    pause
    exit /b 1
)

cd /d "%APP_ROOT%"

set "VENV_DIR=%APP_ROOT%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACT=%VENV_DIR%\Scripts\activate.bat"
set "PYTHONUTF8=1"
set "FLAGS_use_mkldnn=0"
set "FLAGS_use_onednn=0"
REM set "OMP_NUM_THREADS=1"
set "PADDLE_DISABLE_CCACHE_WARNING=1"
set "PYTHONPATH=%APP_ROOT%;%PYTHONPATH%"
set "YSB_TOOL_EDITION=local"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

if not exist "_LOGS_" mkdir "_LOGS_" >nul 2>nul

cls
echo ==========================================
for /f "usebackq delims=" %%V in (`python -c "from ysb.version_info import APP_VERSION; print(APP_VERSION)" 2^>nul`) do set "YSB_APP_VERSION=%%V"
if not defined YSB_APP_VERSION set "YSB_APP_VERSION=current"
echo  YSB Tool Local %YSB_APP_VERSION% - Run Source
echo ==========================================
echo Project root: %APP_ROOT%
echo Virtual env : %VENV_DIR%
echo.

if not exist "%VENV_PY%" (
    echo [ERROR] Local virtual environment was not found.
    echo.
    echo Run this first:
    echo   setup_local_core_venv_v2_1_0.bat
    echo.
    echo This run launcher no longer creates a random venv automatically,
    echo because PaddleOCR should use a supported Python such as 3.11 x64.
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_ACT%" (
    echo [ERROR] venv activate script was not found:
    echo %VENV_ACT%
    echo.
    pause
    exit /b 1
)

call "%VENV_ACT%"
if errorlevel 1 goto ACTIVATE_FAIL

echo Checking Python / required imports...
python -c "import sys, platform; print('Python', sys.version.split()[0], platform.architecture()[0]); raise SystemExit(0 if ((3,9) <= sys.version_info[:2] <= (3,13) and platform.architecture()[0]=='64bit') else 1)"
if errorlevel 1 goto PYTHON_VERSION_FAIL

python -c "import PyQt6; import cv2; import numpy; print('Core imports OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import torch; print('torch OK')"
if errorlevel 1 goto LOCAL_IMPORT_FAIL

python -c "import paddle; print('paddle', paddle.__version__)"
if errorlevel 1 goto PADDLE_IMPORT_FAIL

python -c "import paddle, sys; sys.exit(1 if paddle.__version__.startswith('3.3.') else 0)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [WARNING] PaddlePaddle 3.3.x detected. If OCR text recognition fails with oneDNN/PIR, run fix_paddle_runtime_v2.1.0.bat.
    ver >nul
)

python -c "import paddleocr; print('paddleocr OK')"
if errorlevel 1 goto PADDLEOCR_IMPORT_FAIL

python -c "import importlib.util as u; mods=['transformers','fugashi','unidic_lite']; missing=[m for m in mods if u.find_spec(m) is None]; print('Manga OCR optional deps OK' if not missing else '[INFO] Manga OCR optional deps missing: ' + ', '.join(missing) + ' / run setup_manga_ocr_v2_2_1.bat if you use LOCAL Manga OCR')"

echo.
echo Starting YSB Tool Local...
echo If the app crashes, this window will stay open with the error.
echo.
python "main_local.py" %*
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo ==========================================
    echo  YSB Tool Local exited with error code %APP_EXIT%.
    echo ==========================================
    echo Read the traceback above, then send me the screenshot.
    echo.
    pause
    exit /b %APP_EXIT%
)

exit /b 0

:ACTIVATE_FAIL
echo [ERROR] Failed to activate virtual environment.
pause
exit /b 1

:PYTHON_VERSION_FAIL
echo.
echo [ERROR] Unsupported Python in .venv.
echo PaddleOCR Local should use 64-bit Python 3.11, 3.12, or 3.13.
echo Delete .venv and run setup_local_core_venv_v2_1_0.bat again.
echo.
pause
exit /b 1

:IMPORT_FAIL
echo.
echo [ERROR] Core import test failed.
echo Run setup_local_core_venv_v2_1_0.bat again.
echo.
pause
exit /b 1

:LOCAL_IMPORT_FAIL
echo.
echo [ERROR] Local detector dependency import failed.
echo Run setup_local_core_venv_v2_1_0.bat again.
echo.
pause
exit /b 1

:PADDLE_IMPORT_FAIL
echo.
echo [ERROR] PaddlePaddle import failed.
echo Run setup_local_core_venv_v2_1_0.bat again.
echo.
pause
exit /b 1

:PADDLEOCR_IMPORT_FAIL
echo.
echo [ERROR] PaddleOCR import failed.
echo Run setup_local_core_venv_v2_1_0.bat again.
echo.
pause
exit /b 1
