@echo off
setlocal
cd /d "%~dp0\.."
if "%DOOM_ARENA_MCP_LOG%"=="" set "DOOM_ARENA_MCP_LOG=%~dp0..\src\arena_mcp_stdio.log"
set "PYTHONUNBUFFERED=1"
"C:\Users\muhha\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0doom_arena_mcp.py" %*
