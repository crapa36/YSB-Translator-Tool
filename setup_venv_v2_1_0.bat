@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==================================================
echo YSB Tool v2.1.0 - Setup Local Core venv
echo ==================================================
echo.
echo This setup installs only the supported Local stack:
echo - App/common/lite requirements
echo - comic_text_detector runtime
echo - PaddleOCR CPU
echo - SimpleLaMa local inpainting
echo.
echo Removed from this setup:
echo - experimental OCR readers
echo - local translation packages/models
echo - HuggingFace VLM/OCR test environments
echo.
echo local_models folder will NOT be deleted.
echo.

set "VENV=.venv"
set "PY=%CD%\%VENV%\Scripts\python.exe"

if exist "%PY%" (
    echo Existing .venv found.
    echo This BAT can rebuild .venv as a clean PaddleOCR/comic_detector/LaMa environment.
    echo.
    choice /C YN /N /M "Delete and recreate .venv now? [Y/N]: "
    if errorlevel 2 (
        echo.
        echo Cancelled. No changes were made.
        pause
        exit /b 0
    )
    echo.
    echo Removing existing .venv...
    rmdir /S /Q "%VENV%"
    if exist "%VENV%" (
        echo [ERROR] Failed to remove .venv. Close running Python/YSB windows and retry.
        pause
        exit /b 1
    )
)

echo.
echo [1/8] Creating clean .venv with Python 3.11...
py -3.11 -m venv "%VENV%"
if errorlevel 1 (
    echo [ERROR] Failed to create .venv with py -3.11.
    echo Make sure Python 3.11 is installed and available from the py launcher.
    pause
    exit /b 1
)

set "PY=%CD%\%VENV%\Scripts\python.exe"

echo.
echo [2/8] Python check
"%PY%" --version
if errorlevel 1 goto FAIL

echo.
echo [3/8] Upgrade pip / wheel / base pins
"%PY%" -m pip install --upgrade pip wheel
if errorlevel 1 goto FAIL
"%PY%" -m pip install "setuptools==81.0.0" "numpy==1.26.4" --force-reinstall
if errorlevel 1 goto FAIL

echo.
echo [4/8] Install app requirements
if exist "requirements\common.txt" (
    echo Installing requirements\common.txt
    "%PY%" -m pip install -r "requirements\common.txt"
    if errorlevel 1 goto FAIL
) else (
    echo requirements\common.txt not found. Skipping.
)

if exist "requirements\lite.txt" (
    echo Installing requirements\lite.txt
    "%PY%" -m pip install -r "requirements\lite.txt"
    if errorlevel 1 goto FAIL
) else (
    echo requirements\lite.txt not found. Skipping.
)

echo.
echo [5/8] Install comic_text_detector runtime
"%PY%" -m pip install "torch" "torchvision" "tqdm" "pyclipper" "shapely" "PyYAML" "networkx"
if errorlevel 1 goto FAIL

echo.
echo [6/8] Install PaddleOCR CPU
echo Installing PaddlePaddle CPU 3.2.2
"%PY%" -m pip install "paddlepaddle==3.2.2" -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
if errorlevel 1 goto FAIL

echo Installing PaddleOCR
"%PY%" -m pip install "paddleocr"
if errorlevel 1 goto FAIL

echo.
echo [7/8] Install LOCAL LaMa
"%PY%" -m pip install "simple-lama-inpainting"
if errorlevel 1 goto FAIL

echo.
echo Re-pin compatible base versions after installs
"%PY%" -m pip install "setuptools==81.0.0" "numpy==1.26.4" --force-reinstall
if errorlevel 1 goto FAIL

echo.
echo [8/8] Verify Local core imports
echo.
echo Dependency check:
"%PY%" -m pip check
if errorlevel 1 (
    echo.
    echo [WARN] pip check reported dependency issues.
    echo If import checks below pass, capture this window and continue testing.
    echo.
)

echo.
echo Import checks:
"%PY%" -c "import sys; print('python', sys.version)"
if errorlevel 1 goto FAIL

"%PY%" -c "import numpy; print('numpy', numpy.__version__)"
if errorlevel 1 goto FAIL

"%PY%" -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto FAIL

"%PY%" -c "import cv2; print('cv2 OK')"
if errorlevel 1 goto FAIL

"%PY%" -c "import torch; print('torch', torch.__version__)"
if errorlevel 1 goto FAIL

"%PY%" -c "import paddle; print('paddle', paddle.__version__); paddle.utils.run_check()"
if errorlevel 1 goto FAIL

"%PY%" -c "import paddleocr; print('paddleocr OK')"
if errorlevel 1 goto FAIL

"%PY%" -c "from simple_lama_inpainting import SimpleLama; print('simple-lama-inpainting OK')"
if errorlevel 1 goto FAIL

echo.
echo Local model folder checks:
if exist "third_party\comic_text_detector\comic_text_detector.pt" (
    echo - comic_text_detector model found.
) else (
    echo - comic_text_detector model not found: third_party\comic_text_detector\comic_text_detector.pt
)

if exist "local_models\paddleocr" (
    echo - PaddleOCR local model folder found.
) else (
    echo - PaddleOCR local model folder not found. PaddleOCR may use its own cache/auto-download.
)

if exist "local_models\lama\big-lama.pt" (
    echo - LaMa model found: local_models\lama\big-lama.pt
) else (
    echo - LaMa model not found: local_models\lama\big-lama.pt
)

echo.
echo ==================================================
echo Local core venv setup finished successfully.
echo ==================================================
echo.
echo You can now run:
echo run_local_v2.1.0.bat
echo.
pause
exit /b 0

:FAIL
echo.
echo ==================================================
echo [ERROR] Local core venv setup failed.
echo Please capture the error above.
echo ==================================================
echo.
pause
exit /b 1
