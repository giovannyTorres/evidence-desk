import asyncio
import base64
import datetime as dt
import uuid

import pytest
from sqlalchemy import delete, select

from evidence.config import settings
from evidence.db import Chunk, Document, Job, Session, Version, now
from evidence.domain import process_one


@pytest.mark.parametrize('password', ['AUDIT_INVALID_PASSWORD_' * 12, {'AUDIT_INVALID_PASSWORD_': 'invalid type'}])
def test_invalid_credentials_are_not_reflected_in_validation_errors(client, caplog, password):
    caplog.set_level('INFO', logger='evidence')
    response = client.post('/api/auth/login', json={'email': 'analyst@aurora.example', 'password': password})
    assert response.status_code == 422
    assert 'AUDIT_INVALID_PASSWORD_' not in response.text
    assert 'AUDIT_INVALID_PASSWORD_' not in caplog.text
    assert any(record.name == 'evidence' and '"status": 422' in record.message for record in caplog.records)
    details = response.json()['detail']
    assert details and details[0]['loc'] == ['body', 'password']
    assert all(set(error) == {'loc', 'type', 'msg'} for error in details)


def test_direct_backend_bounds_declared_and_streamed_request_body(client):
    assert client.post('/api/auth/login', content=b'{}', headers={'content-length': str(7 * 1024 * 1024)}).status_code == 413
    response = client.post('/api/auth/login', content=iter([b' ' * 1024 * 1024 for _ in range(7)]), headers={'content-type': 'application/json'})
    assert response.status_code == 413
    assert client.post('/api/auth/login', content=b'{}', headers={'content-length': 'bad'}).status_code == 400


def test_restore_historical_document_content_creates_new_current_version(client):
    original = b'# Restore\nOriginal approved policy.'
    changed = b'# Restore\nChanged policy.'
    doc = client.post('/api/documents', files={'file': ('restore.md', original)}).json()
    try:
        assert client.post('/api/documents', files={'file': ('restore.md', changed)}, data={'document_id': doc['id']}).json()['version'] == 2
        restored = client.post('/api/documents', files={'file': ('restore.md', original)}, data={'document_id': doc['id']}).json()
        assert restored['version'] == 3
        assert client.get(f"/api/documents/{doc['id']}/file").content == original
        assert client.get(f"/api/documents/{doc['id']}/file", params={'version': 0}).status_code == 404
        assert client.post('/api/documents', files={'file': ('restore.md', original)}, data={'document_id': doc['id']}).json()['version'] == 3
    finally:
        client.delete(f"/api/documents/{doc['id']}")


def test_failed_current_index_is_not_searchable(client):
    term = 'auditunique' + uuid.uuid4().hex
    doc = client.post('/api/documents', files={'file': ('search.txt', term.encode())}).json()
    try:
        while asyncio.run(process_one()):
            pass
        assert client.get('/api/search', params={'q': term}).json()['results']
        with Session.begin() as db:
            version = db.scalar(select(Version).where(Version.document_id == doc['id']))
            version.status = 'error'
        assert client.get('/api/search', params={'q': term}).json()['results'] == []
    finally:
        client.delete(f"/api/documents/{doc['id']}")


def test_pdf_parse_failure_is_durable_retryable_worker_state(client):
    response = client.post('/api/documents', files={'file': ('malformed.pdf', b'%PDF-1.7\nnot a valid PDF body')})
    assert response.status_code == 201
    doc = response.json()
    assert doc['status'] == 'queued'
    try:
        while asyncio.run(process_one()):
            pass
        failed = next(d for d in client.get('/api/documents').json() if d['id'] == doc['id'])
        assert failed['status'] == 'error'
        assert failed['error']
        assert client.get('/api/health').status_code == 200
        assert client.post(f"/api/documents/{doc['id']}/retry").status_code == 200
    finally:
        client.delete(f"/api/documents/{doc['id']}")


def test_direct_resource_manipulation_and_expiration(client):
    from evidence.db import LoginSession
    document = client.get('/api/documents').json()[0]
    conversation = client.post('/api/conversations', json={}).json()['id']
    client.post('/api/auth/login', json={'email': 'analyst@meridian.example', 'password': 'demo-evidence'})
    assert client.post('/api/documents', files={'file': ('attempt.txt', b'Unauthorized replacement')}, data={'document_id': document['id']}).status_code == 404
    assert client.get(f"/api/documents/{document['id']}/versions").status_code == 404
    assert client.post(f"/api/documents/{document['id']}/retry").status_code == 404
    assert client.post(f'/api/conversations/{conversation}/cancel').status_code == 404
    assert client.post(f'/api/conversations/{conversation}/messages', json={'scenario_id': 'travel-meals'}).status_code == 404
    import hashlib
    with Session.begin() as db:
        session = db.get(LoginSession, hashlib.sha256(client.cookies['evidence_session'].encode()).hexdigest())
        session.expires = now() - dt.timedelta(seconds=1)
    assert client.get('/api/documents').status_code == 401


def test_query_content_is_absent_from_exported_telemetry(client):
    import json
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))
    canary = 'audit-query-must-not-enter-traces'
    assert client.get('/api/search', params={'q': canary}).status_code == 200
    spans = exporter.get_finished_spans()
    assert spans
    serialized = json.dumps([{'attributes': dict(span.attributes), 'events': [dict(event.attributes) for event in span.events]} for span in spans])
    assert canary not in serialized


@pytest.mark.asyncio
async def test_expired_slow_worker_cannot_overwrite_reclaimed_attempt(monkeypatch):
    from evidence import domain
    monkeypatch.setattr(settings(), 'mode', 'LIVE')
    monkeypatch.setattr(settings(), 'openai_api_key', 'fixture-not-a-key')
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    class ControlledEmbeddings:
        def __init__(self, config):
            pass

        async def embed(self, texts):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
                return [[1.0, 0.0, 0.0]]
            return [[0.0, 1.0, 0.0]]

        async def aclose(self):
            pass

    monkeypatch.setattr(domain, 'ModelGateway', ControlledEmbeddings)
    with Session.begin() as db:
        document = Document(org='audit', mode='LIVE', title='Lease race ' + uuid.uuid4().hex)
        db.add(document)
        db.flush()
        version = Version(document_id=document.id, number=1, filename='race.txt', content_hash='fixture', content=base64.b64encode(b'Original synthetic lease race').decode())
        db.add(version)
        db.flush()
        job = Job(version_id=version.id)
        db.add(job)
        db.flush()
        document_id, version_id, job_id = document.id, version.id, job.id
    first = asyncio.create_task(process_one())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        with Session.begin() as db:
            db.get(Job, job_id).lease_until = now() - dt.timedelta(seconds=1)
        assert await process_one()
        release.set()
        assert await first
        with Session() as db:
            chunk = db.scalar(select(Chunk).where(Chunk.version_id == version_id))
            assert list(chunk.embedding) == [0.0, 1.0, 0.0]
            assert db.get(Job, job_id).attempts == 2
            assert db.get(Job, job_id).state == 'done'
    finally:
        release.set()
        await first
        with Session.begin() as db:
            db.execute(delete(Document).where(Document.id == document_id))
