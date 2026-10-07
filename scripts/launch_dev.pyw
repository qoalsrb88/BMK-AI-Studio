"""Run the source app with a separate local development profile."""
import os
import runpy
import sys
from pathlib import Path


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    profile = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BMK-AI-Studio-dev'
    # Keep startup error logs isolated too; launch.pyw uses this environment key.
    os.environ['BMK_STUDIO_DATA'] = str(profile)
    sys.argv[1:1] = ['--user-directory', str(profile)]
    runpy.run_path(str(root / 'launch.pyw'), run_name='__main__')
