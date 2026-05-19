@echo off
rem YSB robust two-EXE builder
rem Opener icon fix: use absolute icon path because --specpath changes relative path base.
rem version metadata patch: stamps Zerostress8 / YSB role into EXE version resources.
rem lightweight bundle patch: avoids collect-all PyQt6/PIL/Google/cv2 to reduce onefile size and extraction time.
rem splash progress fix: disables static PyInstaller boot splash by default and uses Qt progress splash.
rem launcher full splash restart patch: embeds ysb_splash.png into opener and routes workspace restart through opener.
rem opener splash absolute path fix: PyInstaller --specpath changes relative data path base.
rem This BAT intentionally avoids FOR /F backtick parsing because cmd can break on
rem Python one-liners that contain parentheses.
if /i not "%~1"=="__YSB_RUN__" (
    cmd /k ""%~f0" __YSB_RUN__"
    exit /b
)
shift /1

setlocal EnableExtensions
cd /d "%~dp0"
title YSB Tool EXE Build

set "BUILD_NAME=YSB_Tool_v1.8.1"
set "FINAL_NAME_HEX=ec97adec8b9debb695ec9db420ed88b42076312e382e312e657865"
set "USE_BOOT_SPLASH=0"

set "ENTRY=main.py"
set "OPENER_ENTRY=ysb_file_opener.py"
set "OPENER_NAME=YSBT Luncher"
set "REQ=requirements_ysik_tool.txt"
set "LOG=build_log.txt"
set "ICON_FILE=ysb_icon.ico"
set "SPLASH_FILE=ysb_splash.png"
set "BOOT_SPLASH_FILE=ysb_splash_boot.png"
set "OAUTH_CLIENT_FILE=cloud_oauth_client.json"
set "VERSION_MAIN_FILE=version_main.txt"
set "VERSION_OPENER_FILE=version_opener.txt"
set "ABS_ICON_FILE=%CD%\%ICON_FILE%"
set "ABS_SPLASH_FILE=%CD%\%SPLASH_FILE%"
set "ABS_OPENER_ENTRY=%CD%\%OPENER_ENTRY%"
set "ABS_VERSION_MAIN_FILE=%CD%\%VERSION_MAIN_FILE%"
set "ABS_VERSION_OPENER_FILE=%CD%\%VERSION_OPENER_FILE%"
set "OAUTH_ADD_DATA="
set "PIL_IMAGING_PYD="
set "QT_QWINDOWS_DLL="

echo ==========================================
echo  YSB Tool onefile EXE build
echo ==========================================
echo.
echo BUILD_NAME=%BUILD_NAME%
echo OPENER_NAME=%OPENER_NAME%
echo Main version metadata: %VERSION_MAIN_FILE%
echo Opener version metadata: %VERSION_OPENER_FILE%
echo USE_BOOT_SPLASH=%USE_BOOT_SPLASH%
echo Bundle mode: lightweight ^(limited PyQt6/PIL/Google/cv2 collection^)
echo.

if exist "%LOG%" del /q "%LOG%" >nul 2>nul
if exist "__qt_qwindows_path.txt" del /q "__qt_qwindows_path.txt" >nul 2>nul
if exist "__pil_imaging_path.txt" del /q "__pil_imaging_path.txt" >nul 2>nul

if not exist "%ENTRY%" goto MISSING_ENTRY
if not exist "%OPENER_ENTRY%" goto MISSING_OPENER_ENTRY
if not exist "%ICON_FILE%" goto MISSING_ICON
if not exist "%VERSION_MAIN_FILE%" goto MISSING_VERSION_MAIN
if not exist "%VERSION_OPENER_FILE%" goto MISSING_VERSION_OPENER
if not exist "%SPLASH_FILE%" goto MISSING_QT_SPLASH

if exist "%REQ%" goto REQ_OK
echo Requirements file not found: %REQ%
echo Build will continue by installing required packages directly.
goto CHECK_OAUTH

:REQ_OK
echo Requirements file: %REQ%

:CHECK_OAUTH
if not exist "%OAUTH_CLIENT_FILE%" goto NO_OAUTH
set "OAUTH_ADD_DATA=--add-data %OAUTH_CLIENT_FILE%;."
echo OAuth client: included (%OAUTH_CLIENT_FILE%)
goto CHECK_BOOT_SPLASH

:NO_OAUTH
echo OAuth client: not found (%OAUTH_CLIENT_FILE%) - build continues without embedded OAuth client.
echo Put cloud_oauth_client.json next to this BAT before build if you want Google Login to work out of the box.

:CHECK_BOOT_SPLASH
if not "%USE_BOOT_SPLASH%"=="1" goto BOOT_SPLASH_OFF
if exist "%BOOT_SPLASH_FILE%" goto BOOT_SPLASH_OK
echo Boot splash file not found: %BOOT_SPLASH_FILE%
echo Using %SPLASH_FILE% instead.
set "BOOT_SPLASH_FILE=%SPLASH_FILE%"

:BOOT_SPLASH_OK
echo Boot splash: ON (%BOOT_SPLASH_FILE%)
goto CHECK_PYTHON

:BOOT_SPLASH_OFF
echo Boot splash: OFF

:CHECK_PYTHON
echo.
echo [1/8] Checking Python...
py --version >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
set "PY_CMD=py"
goto PYTHON_OK

:TRY_PYTHON
python --version >nul 2>nul
if errorlevel 1 goto NO_PYTHON
set "PY_CMD=python"

:PYTHON_OK
echo Python command: %PY_CMD%
echo.

echo [2/8] Checking virtual environment...
if exist ".venv\Scripts\python.exe" goto VENV_OK
echo Creating .venv...
%PY_CMD% -m venv .venv
if errorlevel 1 goto VENV_FAIL

:VENV_OK
echo [3/8] Activating virtual environment...
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto ACTIVATE_FAIL

echo [4/8] Installing/updating libraries...
python -m pip install --upgrade pip
if errorlevel 1 goto INSTALL_FAIL

if not exist "%REQ%" goto INSTALL_DIRECT
python -m pip install -r "%REQ%"
if errorlevel 1 goto INSTALL_FAIL
goto INSTALL_BUILD_TOOLS

:INSTALL_DIRECT
python -m pip install PyQt6 opencv-python numpy requests openai replicate pillow google-auth google-auth-oauthlib google-api-python-client google-auth-httplib2
if errorlevel 1 goto INSTALL_FAIL

:INSTALL_BUILD_TOOLS
python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto INSTALL_FAIL

echo.
echo [5/8] Import test and native module path check...

python -c "import PyQt6; print('PyQt6 OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "from PyQt6.QtCore import QLibraryInfo; from pathlib import Path; p=Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))/'platforms'/'qwindows.dll'; print(p.resolve())" > "__qt_qwindows_path.txt"
if errorlevel 1 goto IMPORT_FAIL
set /p QT_QWINDOWS_DLL=<"__qt_qwindows_path.txt"
if not exist "%QT_QWINDOWS_DLL%" goto MISSING_QT_PLATFORM
echo Qt qwindows plugin: %QT_QWINDOWS_DLL%

python -c "import cv2; print('cv2 OK:', cv2.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import numpy; print('numpy OK:', numpy.__version__)"
if errorlevel 1 goto IMPORT_FAIL

python -c "import requests, openai, replicate; from PIL import Image, ImageOps, ImageDraw; import PIL._imaging; print('API/Pillow libs OK')"
if errorlevel 1 goto IMPORT_FAIL

python -c "import pathlib, PIL._imaging; print(pathlib.Path(PIL._imaging.__file__).resolve())" > "__pil_imaging_path.txt"
if errorlevel 1 goto IMPORT_FAIL
set /p PIL_IMAGING_PYD=<"__pil_imaging_path.txt"
if not exist "%PIL_IMAGING_PYD%" goto MISSING_PIL_IMAGING
echo Pillow _imaging: %PIL_IMAGING_PYD%

python -c "import google_auth_oauthlib; import google.oauth2.credentials; import google.auth.transport.requests; import googleapiclient.discovery; print('Google cloud libs OK')"
if errorlevel 1 goto IMPORT_FAIL

echo.
echo [6/8] Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%BUILD_NAME%.spec" del /q "%BUILD_NAME%.spec"
if exist "%OPENER_NAME%.spec" del /q "%OPENER_NAME%.spec"

echo.
echo [7/8] Building main onefile EXE...
echo Build log: %LOG%
echo.

if "%USE_BOOT_SPLASH%"=="1" goto BUILD_MAIN_WITH_BOOT_SPLASH
goto BUILD_MAIN_NO_BOOT_SPLASH

:BUILD_MAIN_NO_BOOT_SPLASH
python -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --icon "%ABS_ICON_FILE%" ^
 --version-file "%ABS_VERSION_MAIN_FILE%" ^
 --add-data "%ICON_FILE%;." ^
 --add-data "%SPLASH_FILE%;." ^
 --hidden-import=PyQt6.QtCore ^
 --hidden-import=PyQt6.QtGui ^
 --hidden-import=PyQt6.QtWidgets ^
 --hidden-import=PyQt6.QtNetwork ^
 --add-binary "%QT_QWINDOWS_DLL%;PyQt6\Qt6\plugins\platforms" ^
 %OAUTH_ADD_DATA% ^
 --name "%BUILD_NAME%" ^
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
 --add-binary "%PIL_IMAGING_PYD%;PIL" ^
 --hidden-import=PIL._imaging ^
 --hidden-import=PIL.Image ^
 --hidden-import=PIL.ImageOps ^
 --hidden-import=PIL.ImageDraw ^
 --hidden-import=PIL.ImageFont ^
 --hidden-import=PIL.ImageFilter ^
 --hidden-import=PIL.ImageEnhance ^
 --hidden-import=PIL.ImageFile ^
 --hidden-import=PIL.PngImagePlugin ^
 --hidden-import=PIL.JpegImagePlugin ^
 --hidden-import=PIL.BmpImagePlugin ^
 --hidden-import=PIL.GifImagePlugin ^
 --hidden-import=PIL.WebPImagePlugin ^
 --hidden-import=PIL.IcoImagePlugin ^
 --hidden-import=PIL.TiffImagePlugin ^
 --hidden-import=PIL._tkinter_finder ^
 --copy-metadata google-auth ^
 --copy-metadata google-auth-oauthlib ^
 --copy-metadata google-api-python-client ^
 --copy-metadata google-auth-httplib2 ^
 --copy-metadata httplib2 ^
 --copy-metadata uritemplate ^
 --hidden-import=google_auth_oauthlib.flow ^
 --hidden-import=google_auth_oauthlib.helpers ^
 --hidden-import=google.oauth2.credentials ^
 --hidden-import=google.auth.transport.requests ^
 --hidden-import=googleapiclient.discovery ^
 --hidden-import=googleapiclient.errors ^
 --hidden-import=googleapiclient.http ^
 --hidden-import=googleapiclient.model ^
 --hidden-import=googleapiclient.discovery_cache ^
 --hidden-import=googleapiclient.discovery_cache.base ^
 "%ENTRY%" > "%LOG%" 2>&1
goto CHECK_MAIN_OUTPUT

:BUILD_MAIN_WITH_BOOT_SPLASH
python -m PyInstaller ^
 --noconfirm ^
 --clean ^
 --onefile ^
 --windowed ^
 --splash "%BOOT_SPLASH_FILE%" ^
 --icon "%ABS_ICON_FILE%" ^
 --version-file "%ABS_VERSION_MAIN_FILE%" ^
 --add-data "%ICON_FILE%;." ^
 --add-data "%SPLASH_FILE%;." ^
 --add-data "%BOOT_SPLASH_FILE%;." ^
 --hidden-import=PyQt6.QtCore ^
 --hidden-import=PyQt6.QtGui ^
 --hidden-import=PyQt6.QtWidgets ^
 --hidden-import=PyQt6.QtNetwork ^
 --add-binary "%QT_QWINDOWS_DLL%;PyQt6\Qt6\plugins\platforms" ^
 %OAUTH_ADD_DATA% ^
 --name "%BUILD_NAME%" ^
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
 --add-binary "%PIL_IMAGING_PYD%;PIL" ^
 --hidden-import=PIL._imaging ^
 --hidden-import=PIL.Image ^
 --hidden-import=PIL.ImageOps ^
 --hidden-import=PIL.ImageDraw ^
 --hidden-import=PIL.ImageFont ^
 --hidden-import=PIL.ImageFilter ^
 --hidden-import=PIL.ImageEnhance ^
 --hidden-import=PIL.ImageFile ^
 --hidden-import=PIL.PngImagePlugin ^
 --hidden-import=PIL.JpegImagePlugin ^
 --hidden-import=PIL.BmpImagePlugin ^
 --hidden-import=PIL.GifImagePlugin ^
 --hidden-import=PIL.WebPImagePlugin ^
 --hidden-import=PIL.IcoImagePlugin ^
 --hidden-import=PIL.TiffImagePlugin ^
 --hidden-import=PIL._tkinter_finder ^
 --copy-metadata google-auth ^
 --copy-metadata google-auth-oauthlib ^
 --copy-metadata google-api-python-client ^
 --copy-metadata google-auth-httplib2 ^
 --copy-metadata httplib2 ^
 --copy-metadata uritemplate ^
 --hidden-import=google_auth_oauthlib.flow ^
 --hidden-import=google_auth_oauthlib.helpers ^
 --hidden-import=google.oauth2.credentials ^
 --hidden-import=google.auth.transport.requests ^
 --hidden-import=googleapiclient.discovery ^
 --hidden-import=googleapiclient.errors ^
 --hidden-import=googleapiclient.http ^
 --hidden-import=googleapiclient.model ^
 --hidden-import=googleapiclient.discovery_cache ^
 --hidden-import=googleapiclient.discovery_cache.base ^
 "%ENTRY%" > "%LOG%" 2>&1
goto CHECK_MAIN_OUTPUT

:CHECK_MAIN_OUTPUT
if exist "dist\%BUILD_NAME%.exe" goto RENAME_MAIN
echo.
echo Main EXE was not created.
echo Check %LOG%.
goto BUILD_FAIL

:RENAME_MAIN
echo.
echo [post] Renaming final EXE...
python -c "from pathlib import Path; final_name=bytes.fromhex('%FINAL_NAME_HEX%').decode('utf-8'); src=Path('dist')/'YSB_Tool_v1.8.1.exe'; dst=Path('dist')/final_name; dst.unlink(missing_ok=True); src.rename(dst); print('Final output:', dst)"
if errorlevel 1 goto RENAME_FAIL

echo.
echo [8/8] Building YSBT launcher...
echo Opener icon: %ABS_ICON_FILE%
echo Opener entry: %ABS_OPENER_ENTRY%
echo Opener splash: %ABS_SPLASH_FILE%
echo --- Building YSBT Luncher --- >> "%LOG%"

python -m PyInstaller ^
 --noconfirm ^
 --onefile ^
 --windowed ^
 --icon "%ABS_ICON_FILE%" ^
 --version-file "%ABS_VERSION_OPENER_FILE%" ^
 --add-data "%ABS_SPLASH_FILE%;." ^
 --hidden-import=tkinter ^
 --name "%OPENER_NAME%" ^
 --distpath "dist" ^
 --workpath "build\opener_build" ^
 --specpath "build\opener_spec" ^
 "%ABS_OPENER_ENTRY%" >> "%LOG%" 2>&1
if errorlevel 1 goto OPENER_BUILD_FAIL

if not exist "dist\%OPENER_NAME%.exe" goto OPENER_MISSING_OUTPUT

echo.
echo Launcher output:
echo dist\%OPENER_NAME%.exe

echo.
echo ==========================================
echo  Build complete
echo.
echo  Final output:
echo  dist\Korean main EXE created
echo  dist\%OPENER_NAME%.exe
echo ==========================================
pause
exit /b 0

:MISSING_ENTRY
echo.
echo Missing file: %ENTRY%
echo Put this BAT in the same folder as main.py.
pause
exit /b 1

:MISSING_OPENER_ENTRY
echo.
echo Missing file: %OPENER_ENTRY%
echo Put this BAT in the same folder as ysb_file_opener.py.
pause
exit /b 1

:MISSING_VERSION_MAIN
echo.
echo Missing file: %VERSION_MAIN_FILE%
pause
exit /b 1

:MISSING_VERSION_OPENER
echo.
echo Missing file: %VERSION_OPENER_FILE%
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

:NO_PYTHON
echo.
echo Python was not found.
echo Install Python first, and enable Add Python to PATH.
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

:MISSING_QT_PLATFORM
echo.
echo Qt platform plugin qwindows.dll was not found.
echo Try deleting .venv and rebuilding, or run:
echo python -m pip install --upgrade --force-reinstall PyQt6 PyQt6-Qt6
pause
exit /b 1

:MISSING_PIL_IMAGING
echo.
echo Pillow native module PIL._imaging was not found.
echo Try deleting .venv and rebuilding, or run:
echo python -m pip install --upgrade --force-reinstall pillow
pause
exit /b 1

:IMPORT_FAIL
echo.
echo Import test failed.
pause
exit /b 1

:OPENER_BUILD_FAIL
echo.
echo Main EXE build succeeded, but YSBT Luncher.exe build failed.
echo Check %LOG%.
pause
exit /b 1

:OPENER_MISSING_OUTPUT
echo.
echo Opener build finished, but dist\%OPENER_NAME%.exe was not found.
echo Check %LOG%.
pause
exit /b 1

:RENAME_FAIL
echo.
echo Build succeeded, but final EXE rename failed.
echo Source:
echo dist\%BUILD_NAME%.exe
echo Target:
echo Korean final EXE name
echo.
echo If a file is open or locked, close it and rebuild.
pause
exit /b 1

:BUILD_FAIL
echo.
echo Build failed.
echo Check %LOG%.
pause
exit /b 1
