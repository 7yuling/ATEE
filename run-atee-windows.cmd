@echo off
setlocal
cd /d "%~dp0"
if exist "C:\Python314\python.exe" (
  set "PYTHON_EXE=C:\Python314\python.exe"
) else (
  set "PYTHON_EXE=python"
)
"%PYTHON_EXE%" services\core-service\check_config.py
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" services\core-service\run_server.py
