"""Portable engineering test entry point. Skipped native gates remain unverified."""
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', 'tests', *sys.argv[1:]], cwd=root))
