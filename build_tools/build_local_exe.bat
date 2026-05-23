@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

set "BUILD_TOOLS_DIR=%~dp0"
for %%I in ("%BUILD_TOOLS_DIR%..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%" || goto :BOOT_FAIL

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

title YSB Tool Local Build

echo YSB Tool Local build bootstrap
echo Project root: %PROJECT_ROOT%
echo.

set "PY_CMD="

REM Local/packaged builds must use Python 3.10-3.12.
REM Prefer 3.11 because PaddleOCR/PaddlePaddle/numpy wheels are stable there.
py -3.11 --version >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3.11"

if not defined PY_CMD (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3.12"
)

if not defined PY_CMD (
    py -3.10 --version >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3.10"
)

if not defined PY_CMD (
    python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Supported Python was not found.
    echo Install Python 3.11.x ^(recommended^) or Python 3.10-3.12, then try again.
    echo Python 3.13/3.14 is not supported for this build because numpy 1.26.4 and Paddle local packages need older wheels.
    goto :END_FAIL
)

echo Using build Python: %PY_CMD%
%PY_CMD% --version

%PY_CMD% "%BUILD_TOOLS_DIR%build_edition_bootstrap.py" local
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo Local build failed. Exit code: %RC%
    echo A bootstrap log should be in the project root: build_bootstrap_local_v*.log
    goto :END_FAIL_CODE
)

echo Local build completed.
goto :END_OK

:BOOT_FAIL
echo Failed to enter project root: %PROJECT_ROOT%
goto :END_FAIL

:END_FAIL
set "RC=1"

:END_FAIL_CODE
echo.
echo This window will stay open so the error can be checked.
pause
exit /b %RC%

:END_OK
echo.
pause
exit /b 0
