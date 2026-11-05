"""Explicit integration audit against a disposable DEMO Compose project; never truncates data."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', default='audit-evidence')
    parser.add_argument('--base-url', default='http://localhost:3201')
    parser.add_argument('--cloud', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('docs/audit-restart.json'))
    args = parser.parse_args()
    if not args.project.startswith('audit-'):
        raise SystemExit('Refusing lifecycle changes outside a project named audit-*')
    root = Path(__file__).resolve().parents[1]
    command = ['docker', 'compose', '-p', args.project, '-f', 'compose.yaml']
    if args.cloud:
        command += ['-f', 'compose.cloud.yaml']
    command += ['-f', 'infra/compose.audit.yaml']

    def compose(*options):
        subprocess.run([*command, *options], cwd=root, check=True, stdout=subprocess.DEVNULL)

    def until(fn, seconds=40):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                value = fn()
                if value:
                    return value
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise AssertionError('Expected persisted state did not become available')

    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        assert client.get('/api/config').json()['mode'] == 'DEMO'
        client.post('/api/auth/login', json={'email': 'analyst@aurora.example', 'password': 'demo-evidence'}).raise_for_status()
        until(lambda: len([d for d in client.get('/api/documents').json() if d['status'] == 'ready']) >= 4)
        compose('stop', 'worker')
        marker = 'audit-persistence-' + uuid.uuid4().hex
        payload = f'Original synthetic {marker}. Retain this evidence through a restart.'.encode()
        response = client.post('/api/documents', files={'file': ('restart.txt', payload)}, data={'title': marker})
        response.raise_for_status()
        doc = response.json()
        assert doc['status'] == 'queued'
        try:
            compose('restart', 'db')
            compose('up', '-d', '--no-build', '--wait', 'db')
            compose('restart', 'api')
            compose('up', '-d', '--no-build', '--wait', 'api')
            assert client.get(f"/api/documents/{doc['id']}/file").content == payload
            assert next(d for d in client.get('/api/documents').json() if d['id'] == doc['id'])['status'] == 'queued'
            compose('up', '-d', '--no-build', '--wait', 'worker')
            until(lambda: next(d for d in client.get('/api/documents').json() if d['id'] == doc['id'])['status'] == 'ready')
            source = client.get('/api/search', params={'q': marker}).json()['results'][0]
            assert source['document_id'] == doc['id']
            convo = client.post('/api/conversations', json={'title': 'Audit restart persistence'}).json()['id']
            answer = client.post(f'/api/conversations/{convo}/messages', json={'scenario_id': 'travel-meals'})
            assert 'event: done' in answer.text
            saved = client.get(f'/api/conversations/{convo}').json()['messages'][-1]
            assert saved['citations'] and '650 MXN' in saved['content']
            compose('restart', 'api', 'worker')
            compose('up', '-d', '--no-build', '--wait', 'api', 'worker')
            restored = client.get(f'/api/conversations/{convo}').json()['messages'][-1]
            assert restored == saved
            assert client.get('/api/sources/' + source['chunk_id']).status_code == 200
        finally:
            compose('up', '-d', '--no-build', '--wait', 'worker')
            client.delete(f"/api/documents/{doc['id']}").raise_for_status()
        assert client.get('/api/sources/' + source['chunk_id']).status_code == 404
    record = {
        'executed_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'project': args.project,
        'mode': 'DEMO', 'external_model_calls': 0,
        'checks': {'session_survives_api_restart': True, 'queued_file_survives_database_restart': True,
                   'worker_resumes_queued_document': True, 'download_bytes_unchanged': True,
                   'conversation_and_citations_survive_api_worker_restart': True,
                   'deleted_document_source_returns_404': True},
        'scope': 'Real container restarts and queued-job recovery. Mid-attempt lease fencing is covered separately by concurrent PostgreSQL regression tests.',
    }
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
