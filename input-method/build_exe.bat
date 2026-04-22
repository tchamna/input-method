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
exit /b 1

:found_python
echo Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" build_pipeline.py
exit /b %errorlevel%
