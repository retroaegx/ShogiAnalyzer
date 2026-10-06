@echo off
cd /d "%~dp0"
python installer\run.py
rem keep the window open so errors stay readable
pause

