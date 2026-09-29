@echo off
cd /d "%~dp0"

:: Launch silently in windowed mode without keeping terminal open
if exist ".\.venv\Scripts\pythonw.exe" (
    start "" ".\.venv\Scripts\pythonw.exe" main.py
) else if exist ".\.venv\Scripts\python.exe" (
    start "" ".\.venv\Scripts\python.exe" main.py
) else (
    start "" pythonw main.py 2>nul || start "" python main.py
)

exit
