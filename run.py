"""Convenience entry point for running the Prompt Generator subsystem."""

import sys
from pathlib import Path

# Add src to python path
src_dir = Path(__file__).parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from prompt_generator.main import main

if __name__ == "__main__":
    main()
