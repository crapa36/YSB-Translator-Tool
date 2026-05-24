@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion

title YSB Tool Single Edition Build Selector
set "BUILD_TOOLS_DIR=%~dp0"

echo YSB Tool build is split by edition.
echo.
echo 1. Build Lite/API package only
echo 2. Build Local package only
echo 3. Exit
echo.
choice /c 123 /n /m "Select: "
set "CHOICE_VALUE=%ERRORLEVEL%"

if "%CHOICE_VALUE%"=="1" goto BUILD_LITE
if "%CHOICE_VALUE%"=="2" goto BUILD_LOCAL
if "%CHOICE_VALUE%"=="3" goto END
goto END

:BUILD_LITE
call "%BUILD_TOOLS_DIR%build_lite_exe.bat"
set "RC=%ERRORLEVEL%"
goto END_WITH_CODE

:BUILD_LOCAL
call "%BUILD_TOOLS_DIR%build_local_exe.bat"
set "RC=%ERRORLEVEL%"
goto END_WITH_CODE


:END_WITH_CODE
exit /b %RC%

:END
exit /b 0
