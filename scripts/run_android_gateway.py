"""Run the Module 2 Android gateway API on the local network."""
import os
import sys
from pathlib import Path
import uvicorn

PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0,str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

if __name__=='__main__':
    uvicorn.run('module_2_accident_response.gateway_api:app',host=os.getenv('M2_GATEWAY_HOST','0.0.0.0'),
        port=int(os.getenv('M2_GATEWAY_PORT','8766')),access_log=False)
