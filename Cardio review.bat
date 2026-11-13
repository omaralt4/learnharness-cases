@echo off
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"
if not exist "%HERE%pick_case.py" goto noscript

set "PY="
if exist "%HERE%python_path.txt" set /p PY=<"%HERE%python_path.txt"
if defined PY if not exist "%PY%" set "PY="
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY if exist "%USERPROFILE%\miniconda3\python.exe" set "PY=%USERPROFILE%\miniconda3\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\anaconda3\python.exe" set "PY=%LOCALAPPDATA%\anaconda3\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\miniconda3\python.exe" set "PY=%LOCALAPPDATA%\miniconda3\python.exe"
if not defined PY if exist "%ProgramData%\anaconda3\python.exe" set "PY=%ProgramData%\anaconda3\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY goto nopython

"%PY%" "%HERE%pick_case.py" review --system cardio
echo.
pause
exit /b

:noscript
echo pick_case.py is not in the same folder as this launcher.
echo This launcher is in: "%HERE%"
echo Put this launcher in the folder that has pick_case.py, scenarios.json and the topics folder.
echo.
pause
exit /b 1

:nopython
echo Couldn't find Python from here.
echo In the terminal where Python works for you, run:
echo     python -c "import sys; print(sys.executable)"
echo Paste the path it prints into a file named python_path.txt in this folder, then try again.
echo.
pause
exit /b 1
