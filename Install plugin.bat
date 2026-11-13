@echo off
setlocal
rem Copies the plugin from this repo into LearnHarness's plugins folder.
rem Only the dist folder is replaced; the app's own data next to it is left alone.
set "SRC=%~dp0plugin\case-images\dist"
set "DEST=%APPDATA%\LearnHarness\data\plugins\case-images\dist"

if not exist "%SRC%\manifest.json" (
  echo Can't find the plugin at "%SRC%".
  echo Run this launcher from the LearnHarness-cases folder.
  echo.
  pause
  exit /b 1
)
if not exist "%APPDATA%\LearnHarness\data" (
  echo Can't find LearnHarness's data folder at "%APPDATA%\LearnHarness\data".
  echo Open LearnHarness, go to Settings, Community plugins, and check the plugins folder path.
  echo.
  pause
  exit /b 1
)

robocopy "%SRC%" "%DEST%" /MIR /NJH /NJS /NP
if errorlevel 8 (
  echo.
  echo The copy failed. Close LearnHarness and try again.
  echo.
  pause
  exit /b 1
)
echo.
echo Installed to "%DEST%".
echo Restart LearnHarness to load the new version.
echo.
pause
exit /b 0
