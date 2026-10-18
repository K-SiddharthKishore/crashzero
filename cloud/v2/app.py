"""CrashZero V2 Community Cloud entry point (CPU, uploads and demo sources)."""
import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
os.environ['CRASHZERO_V2_HOSTED'] = '1'
os.environ['REAL_CALLS_ENABLED'] = 'false'
os.environ['AUTO_TEST_CALL_ENABLED'] = 'false'
os.environ['CALL_PROVIDER'] = 'mock'
runpy.run_path(str(root / 'app.py'), run_name='__main__')
