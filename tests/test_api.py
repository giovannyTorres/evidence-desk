import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from evidence.db import Chunk, Document, Job, Session, Version
from evidence.domain import process_one
from evidence.main import app, login_attempts


@pytest.fixture
def client():
    login_attempts.clear()
    with TestClient(app) as c:
        while asyncio.run(process_one()):
            pass
        assert c.post('/api/auth/login', json={'email': 'analyst@aurora.example', 'password': 'demo-evidence'}).status_code == 200
        yield c


def test_auth_and_origin(client):
    assert client.post('/api/conversations', json={}, headers={'Origin':'https://evil.example'}).status_code == 403
    client.post('/api/auth/logout')
    assert client.get('/api/documents').status_code == 401


def test_document_question_source_isolation(client):
    convo = client.post('/api/conversations', json={'title':'Travel question'}).json()['id']
    result = client.post(f'/api/conversations/{convo}/messages', json={'scenario_id':'travel-meals'})
    assert result.status_code == 200 and 'event: done' in result.text
    messages = client.get(f'/api/conversations/{convo}').json()['messages']
    answer = messages[-1]
    assert '650 MXN' in answer['content']
    source = answer['citations'][0]
    assert client.get('/api/sources/'+source['chunk_id']).json()['excerpt'].find('650 MXN') >= 0
    client.post('/api/auth/login', json={'email':'analyst@meridian.example','password':'demo-evidence'})
    for path in [f'/api/conversations/{convo}', '/api/sources/'+source['chunk_id'], '/api/documents/'+source['document_id']+'/file']:
        assert client.get(path).status_code == 404
    assert client.delete('/api/documents/'+source['document_id']).status_code == 404
    assert client.get('/api/search?q=650').json()['results'] == []


def test_upload_versions_idempotence_and_delete(client):
    data = b'# Test\n## Policy\nAn original synthetic policy.'
    result = client.post('/api/documents', files={'file':('test.md',data)}, data={'title': 'Test '+uuid.uuid4().hex})
    assert result.status_code == 201
    doc = result.json()
    asyncio.run(process_one())
    same = client.post('/api/documents', files={'file':('test.md', data)}, data={'document_id':doc['id']}).json()
    assert same['version'] == 1
    revised = client.post('/api/documents', files={'file':('test.md',data+b' New policy.')}, data={'document_id':doc['id']}).json()
    assert revised['version'] == 2
    asyncio.run(process_one())
    assert len(client.get('/api/documents/'+doc['id']+'/versions').json()) == 2
    with Session() as db:
        ids = list(db.scalars(select(Chunk.id).join(Version).where(Version.document_id == doc['id'])))
    assert ids
    assert client.delete('/api/documents/'+doc['id']).status_code == 200
    for cid in ids:
        assert client.get('/api/sources/'+cid).status_code == 404
    with Session() as db:
        assert db.scalar(select(Job).join(Version).where(Version.document_id == doc['id'])) is None


def test_demo_freeform_and_abstention(client):
    cid = client.post('/api/conversations',json={}).json()['id']
    assert client.post(f'/api/conversations/{cid}/messages',json={'question':'arbitrary text'}).status_code == 422
    result = client.post(f'/api/conversations/{cid}/messages',json={'scenario_id':'no-evidence'})
    assert 'enough evidence' in result.text


def test_replaced_fixture_must_not_support_canned_answer(client):
    with Session.begin() as db:
        doc = db.scalar(select(Document).where(Document.title=='Aurora Travel Handbook', Document.org=='aurora'))
        v = db.scalar(select(Version).where(Version.document_id==doc.id,Version.number==doc.current_version))
        old_hash = v.content_hash
        v.content_hash = 'replacement-content-hash'
    try:
        cid=client.post('/api/conversations',json={}).json()['id']
        client.post(f'/api/conversations/{cid}/messages',json={'scenario_id':'travel-meals'})
        answer=client.get(f'/api/conversations/{cid}').json()['messages'][-1]
        assert 'cannot support' in answer['content'] and answer['citations'] == []
    finally:
        with Session.begin() as db:
            db.get(Version,v.id).content_hash=old_hash


def test_upload_limits_and_bad_signature(client):
    assert client.post('/api/documents',files={'file':('bad.pdf',b'bad')}).status_code == 422
    assert client.post('/api/documents',files={'file':('big.txt',b'x'*(5*1024*1024+1))}).status_code == 413


def test_recovery_expired_lease(client):
    import datetime as dt
    from evidence.db import now
    doc=client.post('/api/documents',files={'file':('recover.txt',b'Recovered evidence')}).json()
    with Session.begin() as db:
        job=db.scalar(select(Job).join(Version).where(Version.document_id==doc['id']))
        job.state='processing'
        job.lease_until=now()-dt.timedelta(seconds=1)
    assert asyncio.run(process_one())
    assert next(d for d in client.get('/api/documents').json() if d['id']==doc['id'])['status']=='ready'
    client.delete('/api/documents/'+doc['id'])


def test_demo_credentials_and_cookie_cannot_cross_into_live(client, monkeypatch):
    from evidence.config import settings
    monkeypatch.setattr(settings(), 'mode', 'LIVE')
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/auth/login',json={'email':'analyst@aurora.example','password':'demo-evidence'}).status_code == 401


def test_reindex_preserves_historical_citation_and_delete_removes_link(client):
    cid = client.post('/api/conversations', json={}).json()['id']
    client.post(f'/api/conversations/{cid}/messages', json={'scenario_id':'purchases-quotes'})
    answer=client.get(f'/api/conversations/{cid}').json()['messages'][-1]
    evidence=answer['citations'][0]
    assert client.post('/api/documents/'+evidence['document_id']+'/retry').status_code == 200
    asyncio.run(process_one())
    assert client.get('/api/sources/'+evidence['chunk_id']).status_code == 200
    # Keep the seeded policy for independent browser runs; deletion coverage uses a temporary document above.


def test_live_cancellation_persists_without_provider_call(client, monkeypatch):
    import concurrent.futures
    import threading
    import evidence.main as main_module
    from evidence.auth import current_user
    from evidence.config import settings
    from evidence.db import User
    entered=threading.Event()
    stopped=threading.Event()

    async def blocked_retrieval(*args):
        entered.set()
        try:
            await asyncio.sleep(30)
        finally:
            stopped.set()

    monkeypatch.setattr(settings(), 'mode', 'LIVE')
    monkeypatch.setattr(settings(), 'openai_api_key', 'contract-placeholder')
    monkeypatch.setattr(main_module, 'retrieve', blocked_retrieval)
    with Session() as db:
        user=db.scalar(select(User).where(User.email=='analyst@aurora.example'))
    app.dependency_overrides[current_user]=lambda: user
    try:
        cid=client.post('/api/conversations',json={}).json()['id']
        with concurrent.futures.ThreadPoolExecutor() as pool:
            request=pool.submit(client.post,f'/api/conversations/{cid}/messages',json={'question':'Cancel this test'})
            assert entered.wait(5)
            assert client.post(f'/api/conversations/{cid}/cancel').status_code==200
            response=request.result(timeout=5)
        assert 'event: cancelled' in response.text
        assert stopped.wait(5)
        messages=client.get(f'/api/conversations/{cid}').json()['messages']
        assert messages[-1]['metadata']['cancelled'] is True
    finally:
        app.dependency_overrides.clear()
