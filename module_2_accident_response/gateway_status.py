"""Local Android gateway connection details for the Streamlit dashboard."""
import os
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def phone_gateway_url():
    configured=os.getenv('M2_GATEWAY_URL','').strip().rstrip('/')
    if configured:
        return configured
    port=int(os.getenv('M2_GATEWAY_PORT','8766'))
    for interface in ('en0','en1'):
        try:
            ip=subprocess.run(['ipconfig','getifaddr',interface],capture_output=True,text=True,timeout=1).stdout.strip()
            if ip:
                return f'http://{ip}:{port}'
        except (OSError,subprocess.TimeoutExpired):
            pass
    try:
        ip=socket.gethostbyname(socket.gethostname())
        if not ip.startswith('127.'):
            return f'http://{ip}:{port}'
    except OSError:
        pass
    return f'http://<this-mac-wifi-address>:{port}'


def gateway_reachable():
    token=os.getenv('M2_GATEWAY_TOKEN','')
    if len(token)<32:
        return False
    port=int(os.getenv('M2_GATEWAY_PORT','8766'))
    request=Request(f'http://127.0.0.1:{port}/api/v1/health',headers={'Authorization':'Bearer '+token})
    try:
        with urlopen(request,timeout=1) as response:
            return response.status==200
    except (HTTPError,URLError,TimeoutError,OSError):
        return False


def phone_monitoring(repository,within_seconds=15):
    last=repository.last_gateway_poll()
    return bool(last and 0<=time.time()-last<=within_seconds)
