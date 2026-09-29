#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Detect python executable
if [ -f "./.venv/bin/python" ]; then
    PY_BIN="./.venv/bin/python"
elif [ -f "./.venv/bin/python3" ]; then
    PY_BIN="./.venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PY_BIN="python3"
else
    PY_BIN="python"
fi

# Run completely detached in background
nohup $PY_BIN main.py >/dev/null 2>&1 &

# If executed via macOS Terminal, automatically close terminal window
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_web_ui")' 2>/dev/null &
exit 0
