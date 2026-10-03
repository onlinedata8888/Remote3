@echo off
cd /d "%~dp0"
py -m pip install vgamepad
py gamepad_server.py %*
pause
