@echo off
setlocal

set PYTHON_EXE=

:: Try py launcher first (Python for Windows installer registers this)
where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=py
    goto found_python
)

:: Try python3
where python3 >nul 2>&1
if not errorlevel 1 (
    set PYTHON_EXE=python3
    goto found_python
)

:: Try full path for Python 3.x in common install locations
for %%V in (314 313 312 311 310) do (
    if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
        set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe
        goto found_python
    )
)

echo Python not found. Please install Python from https://python.org and re-run.
pause
exit /b 1

:found_python
echo Using Python: %PYTHON_EXE%

echo Step 1: Installing dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pyinstaller keyboard

echo Step 2: Building TextExpander.exe...
"%PYTHON_EXE%" -m PyInstaller --clean --noconfirm --onefile --name TextExpander text_expansion.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo Step 3: Creating share_with_colleague folder...
.\dist\TextExpander.exe --build-share ".\share_with_colleague"

echo.
echo Done. EXE is in dist\TextExpander.exe
echo Share folder is in share_with_colleague\
pause
