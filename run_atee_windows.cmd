@echo off
setlocal
cd /d "%~dp0"
if exist "C:\Python314\python.exe" (
  "C:\Python314\python.exe" services\core-service\run_server.py
) else (
  python services\core-service\run_server.py
)

