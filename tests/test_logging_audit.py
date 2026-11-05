import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def test_actual_uvicorn_logs_and_console_traces_omit_query_values(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'services/api'), 'OTEL_CONSOLE': 'true'}
    output = tmp_path / 'server.log'
    with output.open('w') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'evidence.main:app', '--host', '127.0.0.1', '--port', str(port)], env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=2) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError('Audit subprocess did not become ready')
                assert client.get('/api/health', params={'q': 'sensitive-query-audit-canary'}).status_code == 200
        finally:
            process.terminate()
            process.wait(timeout=10)
    contents = output.read_text()
    assert '"event": "request"' in contents
    assert 'sensitive-query-audit-canary' not in contents
