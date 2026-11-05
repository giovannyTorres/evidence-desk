"""Tests never reuse the application's configured database or model credentials."""
import os
from urllib.parse import unquote, urlsplit

import pytest


test_database_url = os.getenv('TEST_DATABASE_URL', 'postgresql+psycopg://evidence:evidence@localhost:5541/evidence_test')
if not unquote(urlsplit(test_database_url).path).removeprefix('/').endswith('_test'):
    raise pytest.UsageError('TEST_DATABASE_URL must name a dedicated database ending in _test')
os.environ['DATABASE_URL'] = test_database_url
os.environ['MODE'] = 'DEMO'
# Explicit LIVE smoke tests remain opt-in; ordinary test requests cannot accidentally use configured keys.
if os.getenv('RUN_LIVE') != '1':
    os.environ['OPENAI_API_KEY'] = ''
    os.environ['GEMINI_API_KEY'] = ''


@pytest.fixture
def client():
    import asyncio
    from fastapi.testclient import TestClient
    from evidence.domain import process_one
    from evidence.main import app, login_attempts

    login_attempts.clear()
    with TestClient(app) as client:
        while asyncio.run(process_one()):
            pass
        assert client.post('/api/auth/login', json={'email': 'analyst@aurora.example', 'password': 'demo-evidence'}).status_code == 200
        yield client
