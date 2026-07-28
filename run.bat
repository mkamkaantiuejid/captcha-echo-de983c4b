@echo off
REM Windows production/dev launcher (headed browser)
if not defined BROWSER_HEADLESS set BROWSER_HEADLESS=0
if not defined PORT set PORT=8877
python -m playwright install chromium 2>nul
python server.py
