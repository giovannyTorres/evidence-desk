"""Trust/scoping tests, with NVIDIA HTTP fixtures explicitly limited to transport tests."""
import hashlib
import asyncio
import json
import uuid

import httpx
import pytest
from sqlalchemy import delete

from evidence.config import Settings
from evidence.db import Chunk, Document, Session, Version
from evidence.domain import retrieve
from evidence.migrate import migrate
from evidence.ontology import (AutoOntologyClient, OntologyError, SemanticContext, Snapshot,
                               Term, load_snapshot, resolve_context, term_digest)
from evidence.ontology_runner import observe


def term_value(**updates):
    value = {'id': 'term-meals', 'name': 'Meal allowance', 'description': 'Daily domestic meal limit.',
             'synonyms': ['per diem', 'viáticos'], 'name_certified': True, 'description_certified': True}
    value.update(updates)
    return {**value, 'sha256': term_digest(value)}


def snapshot_value(**updates):
    value = {'schema_version': 1, 'application': 'evidence-desk', 'snapshot_id': 'review-1',
             'source': 'glossary', 'source_commit': 'reviewed-source',
             'scope': {'org': 'aurora', 'mode': 'LIVE'}, 'certified': True,
             'approved_by': 'test-reviewer', 'terms': [term_value()], 'bindings': []}
    value.update(updates)
    return value


def write_snapshot(tmp_path, value):
    path = tmp_path / 'review.json'
    raw = json.dumps(value, ensure_ascii=False).encode()
    path.write_bytes(raw)
    return str(path), hashlib.sha256(raw).hexdigest()


def config_for(path, digest, **values):
    return Settings(mode='LIVE', ontology_mode='glossary',
                    ontology_snapshots={'aurora:LIVE': {'path': path, 'sha256': digest}}, **values)


def test_digest_is_canonical_but_covers_meaning_and_certification():
    value = term_value()
    assert term_digest(value) == term_digest({**value, 'synonyms': ['viáticos', 'per diem', 'per diem']})
    assert term_digest(value) != term_digest({**value, 'description': 'A different limit'})
    assert term_digest(value) != term_digest({**value, 'name_certified': False})


@pytest.mark.parametrize('change', [
    {'application': 'other-app'}, {'schema_version': 2}, {'certified': False},
    {'scope': {'org': 'meridian', 'mode': 'LIVE'}}, {'scope': {'org': 'aurora', 'mode': 'DEMO'}},
    {'terms': [term_value(name_certified=False)]},
    {'terms': [{**term_value(), 'description': 'Changed without review'}]},
    {'terms': [term_value(), term_value()]},
])
def test_unapproved_snapshot_never_becomes_context(tmp_path, change):
    path, digest = write_snapshot(tmp_path, snapshot_value(**change))
    with pytest.raises(OntologyError):
        load_snapshot(path, digest, 'aurora', 'LIVE')


def test_file_digest_and_duplicate_json_keys_are_rejected(tmp_path):
    path, digest = write_snapshot(tmp_path, snapshot_value())
    with pytest.raises(OntologyError):
        load_snapshot(path, '0' * 64, 'aurora', 'LIVE')
    raw = b'{"application":"evidence-desk","application":"other"}'
    (tmp_path / 'review.json').write_bytes(raw)
    with pytest.raises(OntologyError):
        load_snapshot(path, hashlib.sha256(raw).hexdigest(), 'aurora', 'LIVE')


async def test_real_nvidia_get_envelopes_pagination_and_revision_contract():
    term = Term.model_validate(term_value())
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == 'GET' and request.headers['x-api-key'] == 'test-secret'
        if request.url.path == '/api/terms':
            assert request.url.params['query'] == term.name
            if request.url.params['skip'] == '0':
                return httpx.Response(200, json={'terms': [{'id': 'another'}] * 50, 'total': 51})
            return httpx.Response(200, json={'terms': [{'id': term.id}], 'total': 51})
        return httpx.Response(200, json={'data': {**term.model_dump(exclude={'sha256'}), 'tables': []}})

    client = AutoOntologyClient('http://127.0.0.1:3000', 'test-secret', transport=httpx.MockTransport(handler))
    try:
        await client.verify(term)
        assert len(requests) == 3
        assert requests[-1].url.path == '/api/terms/' + term.id
    finally:
        await client.aclose()


@pytest.mark.parametrize('failure', ['401', '403', '500', 'redirect', 'shape', 'changed', 'uncertified', 'timeout'])
async def test_remote_failure_or_changed_revision_is_sanitized(failure):
    term = Term.model_validate(term_value())

    def handler(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('PRIVATE provider body token', request=request)
        if failure.isdigit():
            return httpx.Response(int(failure), text='PRIVATE provider body token')
        if failure == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://other.example/'})
        if request.url.path == '/api/terms':
            return httpx.Response(200, json={'data': []} if failure == 'shape' else
                                  {'terms': [{'id': term.id}], 'total': 1})
        data = term.model_dump(exclude={'sha256'})
        data['description' if failure == 'changed' else 'name_certified'] = (
            'Changed remotely' if failure == 'changed' else False)
        return httpx.Response(200, json={'data': data})

    client = AutoOntologyClient('https://ontology.example', 'PRIVATE', transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(OntologyError) as error:
            await client.verify(term)
        assert 'PRIVATE' not in str(error.value)
    finally:
        await client.aclose()


async def test_demo_off_and_wrong_scope_do_not_call_nvidia(tmp_path):
    path, digest = write_snapshot(tmp_path, snapshot_value(source='auto_ontology'))
    config = config_for(path, digest, auto_ontology_url='https://ontology.example')

    def forbidden(_):
        raise AssertionError('Network is forbidden')

    transport = httpx.MockTransport(forbidden)
    assert not (await resolve_context('per diem', 'aurora', 'DEMO', config, 'auto_ontology',
                                     transport=transport)).terms
    assert not (await resolve_context('per diem', 'aurora', 'LIVE', config, 'off',
                                     transport=transport)).terms
    context = await resolve_context('per diem', 'meridian', 'LIVE', config, 'auto_ontology', transport=transport)
    assert context.audit['status'] == 'unavailable_baseline_fallback'


async def test_total_remote_budget_spans_all_requests_and_falls_back(tmp_path):
    path, digest = write_snapshot(tmp_path, snapshot_value(source='auto_ontology'))
    config = config_for(path, digest, auto_ontology_url='https://ontology.example', ontology_timeout=.5)
    calls = []

    async def slow(request):
        calls.append(request.url.path)
        await asyncio.sleep(.3)
        return httpx.Response(200, json={'terms': [{'id': 'term-meals'}], 'total': 1} if
                              request.url.path == '/api/terms' else {'data': term_value()})

    transport = httpx.MockTransport(slow)
    context = await resolve_context('per diem', 'aurora', 'LIVE', config, 'auto_ontology', transport=transport)
    assert len(calls) == 2 and context.audit['status'] == 'unavailable_baseline_fallback'
    with pytest.raises(OntologyError, match='total request budget'):
        await resolve_context('per diem', 'aurora', 'LIVE', config, 'auto_ontology',
                              strict=True, transport=transport)


async def test_per_organization_origins_and_tokens_do_not_cross(tmp_path, monkeypatch):
    aurora = snapshot_value(source='auto_ontology')
    path_a, digest_a = write_snapshot(tmp_path, aurora)
    other_path = tmp_path / 'meridian'
    other_path.mkdir()
    meridian = snapshot_value(source='auto_ontology', scope={'org': 'meridian', 'mode': 'LIVE'},
                              terms=[term_value(id='meridian-meals', description='Meridian reviewed meaning')])
    path_b, digest_b = write_snapshot(other_path, meridian)
    monkeypatch.setenv('AO_AURORA_TEST_TOKEN', 'aurora-token')
    monkeypatch.setenv('AO_MERIDIAN_TEST_TOKEN', 'meridian-token')
    config = Settings(mode='LIVE', ontology_mode='auto_ontology',
        auto_ontology_url='https://global-must-not-be-used.example', auto_ontology_api_token='global-token',
        ontology_snapshots={'aurora:LIVE': {'path': path_a, 'sha256': digest_a},
                            'meridian:LIVE': {'path': path_b, 'sha256': digest_b}},
        auto_ontology_connections={'aurora:LIVE': {'url': 'http://127.0.0.1:3210', 'token_env': 'AO_AURORA_TEST_TOKEN'},
                                  'meridian:LIVE': {'url': 'http://127.0.0.1:3211', 'token_env': 'AO_MERIDIAN_TEST_TOKEN'}})
    seen = []

    def handler(request):
        value = aurora if request.url.port == 3210 else meridian
        term = value['terms'][0]
        expected_token = 'aurora-token' if request.url.port == 3210 else 'meridian-token'
        assert request.headers['x-api-key'] == expected_token
        seen.append((request.url.port, request.headers['x-api-key']))
        return httpx.Response(200, json={'terms': [{'id': term['id']}], 'total': 1} if
                              request.url.path == '/api/terms' else {'data': term})

    for org in ('aurora', 'meridian'):
        result = await resolve_context('per diem', org, 'LIVE', config, strict=True,
                                       transport=httpx.MockTransport(handler))
        assert result.audit['status'] == 'verified'
    assert seen == [(3210, 'aurora-token'), (3210, 'aurora-token'),
                    (3211, 'meridian-token'), (3211, 'meridian-token')]
    del config.auto_ontology_connections['meridian:LIVE']
    with pytest.raises(OntologyError, match='scoped token reference'):
        await resolve_context('per diem', 'meridian', 'LIVE', config, strict=True,
                              transport=httpx.MockTransport(handler))


async def test_adapter_rejects_goldens_and_does_not_substitute_mock_auto_ontology(monkeypatch):
    request = {'case': {'id': 'case1', 'kind': 'rag', 'prompt': 'per diem', 'context': '',
                        'expected': {'answer': 'GOLDEN MUST NOT BE USED'}},
               'arm': 'baseline', 'options': {'org': 'aurora'}}
    assert (await observe(request))['status'] == 'error'
    del request['case']['expected']
    request['arm'] = 'auto_ontology'
    monkeypatch.setattr('evidence.ontology_runner.dedicated_database', lambda: None)
    result = await observe(request)
    assert result['status'] == 'skipped' and result['output'] is None
    assert result['provenance']['scope'] == 'retrieval_only'


async def test_adapter_uses_prompt_not_supplied_context_or_goldens(monkeypatch):
    class LocalGateway(LocalEmbeddings):
        dimensions = 3

        def __init__(self, *_):
            pass

        async def aclose(self):
            pass

    seen = []

    async def actual_retrieval(question, org, gateway, audit, **_):
        seen.append((question, org))
        audit.update(status='disabled')
        return [{'chunk_id': 'original-chunk', 'excerpt': 'Original evidence only.'}]

    monkeypatch.setattr('evidence.ontology_runner.dedicated_database', lambda: None)
    monkeypatch.setattr('evidence.ontology_runner.OllamaEmbeddings', LocalGateway)
    monkeypatch.setattr('evidence.domain.retrieve', actual_retrieval)
    request = {'case': {'id': 'case1', 'kind': 'rag', 'prompt': 'Actual question',
                        'context': 'Injected golden answer MUST NOT BE USED'},
               'arm': 'baseline', 'options': {'org': 'aurora'}}
    result = await observe(request)
    assert seen == [('Actual question', 'aurora')]
    assert result['output']['answer'] == 'Original evidence only.'
    assert result['output']['citations'] == ['original-chunk']


class LocalEmbeddings:
    embedding_provider = 'ollama'
    embedding_model = 'local-test'

    async def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


async def test_scope_current_version_hash_and_identity_are_rechecked_in_postgres():
    migrate()
    documents = []
    versions = []
    chunks = []
    org = 'ontology-' + uuid.uuid4().hex
    content_hash = hashlib.sha256(b'approved text').hexdigest()
    try:
        with Session.begin() as db:
            for owner, mode in [(org, 'LIVE'), ('other-' + org, 'LIVE'), (org, 'DEMO')]:
                document = Document(org=owner, mode=mode, title='Scoped evidence')
                db.add(document)
                db.flush()
                documents.append(document.id)
                version = Version(document_id=document.id, number=1, filename='fixture.txt', content='',
                    content_hash=content_hash, status='ready', provider='ollama', model='local-test', dimensions=3)
                db.add(version)
                db.flush()
                versions.append(version.id)
                chunk = Chunk(version_id=version.id, location='Meals', text='Meal allowance is 650 MXN.',
                              embedding=[1.0, 0.0, 0.0])
                db.add(chunk)
                db.flush()
                chunks.append(chunk.id)
        value = snapshot_value(scope={'org': org, 'mode': 'LIVE'}, bindings=[
            {'term_id': 'term-meals', 'chunk_id': chunk, 'document_id': document,
             'document_version': 1, 'content_sha256': content_hash}
            for chunk, document in zip(chunks, documents)])
        snapshot = Snapshot.model_validate(value)
        context = SemanticContext(snapshot.terms, snapshot.bindings,
                                  {'strategy': 'glossary', 'status': 'verified', 'snapshot_id': 'review-1'})
        audit = {}
        results = await retrieve('per diem', org, LocalEmbeddings(), audit, semantic_context=context)
        assert [row['chunk_id'] for row in results] == [chunks[0]]
        assert results[0]['semantic_context']['terms'][0]['id'] == 'term-meals'
        assert audit['authorized_bindings'] == 1 and audit['rejected_bindings'] == 2
        with Session.begin() as db:
            db.get(Version, versions[0]).content_hash = hashlib.sha256(b'changed').hexdigest()
        results = await retrieve('per diem', org, LocalEmbeddings(), semantic_context=context)
        assert 'semantic_context' not in results[0]
        with Session.begin() as db:
            db.get(Document, documents[0]).current_version = 2
        assert await retrieve('per diem', org, LocalEmbeddings(), semantic_context=context) == []
        with Session.begin() as db:
            db.get(Document, documents[0]).current_version = 1
            db.get(Version, versions[0]).provider = 'openai'
        with pytest.raises(ValueError, match='incompatible'):
            await retrieve('per diem', org, LocalEmbeddings())
    finally:
        with Session.begin() as db:
            db.execute(delete(Document).where(Document.id.in_(documents)))
