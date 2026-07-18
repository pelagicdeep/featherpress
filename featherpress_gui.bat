@echo off
cd /d "%~dp0"
start "" pythonw featherpress_gui.py
if errorlevel 1 python featherpress_gui.py
