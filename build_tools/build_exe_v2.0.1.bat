@echo off
chcp 65001 >nul
setlocal EnableExtensions

title YSB Tool EXE Build

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "BUILD_TOOLS_DIR=%~dp0"
for %%I in ("%BUILD_TOOLS_DIR%..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo Failed to enter project root: %PROJECT_ROOT%
    pause
    exit /b 1
)

echo Project root: %PROJECT_ROOT%
echo.

set "VENV_DIR=%PROJECT_ROOT%\.venv"
set "PY_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"

set "PY_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=python"
)

if not exist "%PY_EXE%" (
    if not defined PY_CMD (
        echo Python was not found. Install Python 3.10+ and try again.
        pause
        exit /b 1
    )
    echo [1/8] Creating virtual environment...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/8] Virtual environment found.
)

echo [2/8] Upgrading pip...
"%PY_EXE%" -m pip install --upgrade pip

if exist "%PROJECT_ROOT%\requirements_ysik_tool.txt" (
    echo.
    echo [3/8] Installing project requirements...
    "%PIP_EXE%" install -r "%PROJECT_ROOT%\requirements_ysik_tool.txt"
    if errorlevel 1 (
        echo Failed to install requirements.
        pause
        exit /b 1
    )
) else (
    echo.
    echo [3/8] requirements_ysik_tool.txt not found. Skipping project requirements.
)

echo.
echo [4/8] Installing build requirements...
"%PIP_EXE%" install --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo [5/8] Build environment check...
"%PY_EXE%" "%BUILD_TOOLS_DIR%build_probe.py"
if errorlevel 1 (
    echo Build environment check failed.
    pause
    exit /b 1
)

echo.
echo [6/8] Cleaning old build files...
if exist "%PROJECT_ROOT%\build" rmdir /s /q "%PROJECT_ROOT%\build"
if exist "%PROJECT_ROOT%\dist\역식붕이 툴 v2.0.1.exe" del /q "%PROJECT_ROOT%\dist\역식붕이 툴 v2.0.1.exe"
if exist "%PROJECT_ROOT%\dist\YSB_Launcher.exe" del /q "%PROJECT_ROOT%\dist\YSB_Launcher.exe"
if exist "%PROJECT_ROOT%\build_log.txt" del /q "%PROJECT_ROOT%\build_log.txt"

echo.
echo [7/8] Building optimized onefile EXE files...
"%PY_EXE%" "%BUILD_TOOLS_DIR%build_pyinstaller.py"
if errorlevel 1 (
    echo.
    echo Build failed.
    echo Check "%PROJECT_ROOT%\build_log.txt".
    pause
    exit /b 1
)

echo.
echo [8/8] Build completed.
echo Output:
echo   "%PROJECT_ROOT%\dist\역식붕이 툴 v2.0.1.exe"
echo   "%PROJECT_ROOT%\dist\YSB_Launcher.exe"
echo.
pause
exit /b 0
