@echo off
setlocal
set "ROOT=%~dp0..\.."
pushd "%ROOT%" >nul

set "NODE_EXE=D:\Node.js\node.exe"
if not exist "%NODE_EXE%" set "NODE_EXE=node"

"%NODE_EXE%" "%ROOT%\scripts\frontend-live-production-rehearsal.mjs" %*
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
