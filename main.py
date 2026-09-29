"""
Prompt Generator — Desktop Application Entrypoint.
Starts the backend server and launches standalone window on Windows and macOS.
"""

import os
import sys
import time
import subprocess
import threading
import platform
from pathlib import Path

# Ensure stdout/stderr are valid streams in windowed (console=False) mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Hide console window immediately on Windows if running in terminal
if sys.platform == "win32":
    try:
        import ctypes
        hWnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hWnd:
            ctypes.windll.user32.ShowWindow(hWnd, 0)
    except Exception:
        pass

# Setup paths (works for both frozen executable and development mode)
if getattr(sys, 'frozen', False):
    _ROOT = Path(sys._MEIPASS)
else:
    _ROOT = Path(__file__).resolve().parent

if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_ROOT / "web_gui") not in sys.path:
    sys.path.insert(0, str(_ROOT / "web_gui"))

def open_desktop_window(url="http://127.0.0.1:5000"):
    """Open the web interface in an app window without browser tabs/address bar."""
    time.sleep(1.2)
    system = platform.system()

    if system == 'Windows':
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        chosen = None
        for path in candidates:
            if os.path.isfile(path):
                chosen = path
                break

        if chosen:
            subprocess.Popen([chosen, f"--app={url}", "--window-size=1250,880"])
        else:
            import webbrowser
            webbrowser.open(url)

    elif system == 'Darwin':
        # macOS
        if os.path.isdir("/Applications/Google Chrome.app"):
            subprocess.Popen(["open", "-na", "Google Chrome", "--args", f"--app={url}", "--window-size=1250,880"])
        elif os.path.isdir("/Applications/Microsoft Edge.app"):
            subprocess.Popen(["open", "-na", "Microsoft Edge", "--args", f"--app={url}", "--window-size=1250,880"])
        elif os.path.isdir("/Applications/Brave Browser.app"):
            subprocess.Popen(["open", "-na", "Brave Browser", "--args", f"--app={url}", "--window-size=1250,880"])
        else:
            import webbrowser
            webbrowser.open(url)
    else:
        import webbrowser
        webbrowser.open(url)

def main():
    # Launch UI window in a separate thread
    t = threading.Thread(target=open_desktop_window, daemon=True)
    t.start()

    # Import and run server
    from web_gui.server import app
    print("===================================================")
    print("  Prompt Generator - Antigravity CLI Subsystem")
    print("===================================================")
    print("Application server running on http://127.0.0.1:5000")
    print("Close this terminal window or press Ctrl+C to exit.")
    app.run(host='127.0.0.1', port=5000)

if __name__ == '__main__':
    main()
