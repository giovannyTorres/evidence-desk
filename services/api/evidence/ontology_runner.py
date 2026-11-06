"""Opt-in PostgreSQL/Ollama retrieval benchmark; never an answer-quality claim.

The adapter consumes prompts and scope, never evaluator expectations. Preparation
materializes goldens separately from current original chunk IDs in a dedicated DB.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid
from urllib.parse import unquote, urlsplit

import httpx

from .config import Settings, settings
from .ontology import OntologyError, public_origin, resolve_context, strict_json, term_digest

ROOT = Path(__file__).resolve().parents[3]
ABSTENTION = 'I could not find enough evidence in the authorized documents to answer this question.'


class OllamaEmbeddings:
    embedding_provider = 'ollama'

    def __init__(self, model: str = 'qwen3-embedding:0.6b', origin: str = 'http://127.0.0.1:11434'):
        origin = public_origin(origin)
        if urlsplit(origin).hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('This benchmark only calls local Ollama')
        self.embedding_model = model
        self.client = httpx.AsyncClient(base_url=origin, timeout=120, follow_redirects=False)
        self.dimensions = 0

    async def embed(self, texts):
        response = await self.client.post('/api/embed', json={
            'model': self.embedding_model, 'input': texts, 'truncate': False})
        response.raise_for_status()
        data = response.json()
        vectors = data.get('embeddings')
        if data.get('model') != self.embedding_model or not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError('Local embedding identity or count mismatch')
        for vector in vectors:
            if (not isinstance(vector, list) or not vector or len(vector) > 3072 or
                    any(type(value) not in (float, int) or not math.isfinite(value) for value in vector)):
                raise ValueError('Invalid local embedding')
            if self.dimensions and len(vector) != self.dimensions:
                raise ValueError('Local embedding dimension changed')
            self.dimensions = len(vector)
        return vectors

    async def aclose(self):
        await self.client.aclose()


def dedicated_database():
    value = os.getenv('EVIDENCE_BENCHMARK_DATABASE_URL', '')
    name = unquote(urlsplit(value).path).removeprefix('/')
    if not value or not name.endswith('_test') or 'benchmark' not in name:
        raise ValueError('Set EVIDENCE_BENCHMARK_DATABASE_URL to a dedicated *_benchmark*_test database')
    os.environ['DATABASE_URL'] = value
    settings.cache_clear()


async def observe(request: dict) -> dict:
    provenance = {'scope': 'retrieval_only', 'generation': 'extractive'}
    try:
        case, arm, options = request['case'], request['arm'], request.get('options', {})
        if arm not in {'baseline', 'glossary', 'auto_ontology'} or case.get('kind') != 'rag':
            raise ValueError('Unsupported adapter request')
        if set(case) - {'id', 'kind', 'prompt', 'context'}:
            raise ValueError('Evaluator expectations must never be passed to the adapter')
        question = case['prompt']
        if not isinstance(question, str) or not question.strip() or len(question) > 20000:
            raise ValueError('Invalid question')
        org = options.get('scopes_by_case', {}).get(case['id'], options.get('org'))
        if not isinstance(org, str) or not org:
            raise ValueError('An explicit case organization is required')
        dedicated_database()
        config = Settings(mode='LIVE', ontology_mode='off' if arm == 'baseline' else arm,
                          ontology_snapshots=options.get('snapshots', {}))
        context = await resolve_context(question, org, 'LIVE', config, arm, strict=True)
        gateway = OllamaEmbeddings(options.get('embedding_model', 'qwen3-embedding:0.6b'),
                                   os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434'))
        audit: dict = {}
        try:
            from .domain import retrieve
            sources = await retrieve(question, org, gateway, audit, config=config, semantic_context=context)
        finally:
            await gateway.aclose()
        provenance.update({'org': org, 'mode': 'LIVE', 'embedding_provider': gateway.embedding_provider,
                           'embedding_model': gateway.embedding_model, 'embedding_dimensions': str(gateway.dimensions),
                           'ontology_status': audit['status'],
                           'ontology_http_requests': str(audit.get('remote_requests', 0))})
        if audit.get('snapshot_sha256'):
            provenance['snapshot_sha256'] = audit['snapshot_sha256']
        if audit.get('rejected_bindings'):
            return {'status': 'skipped', 'execution': 'live', 'output': None, 'trace': [{'semantic': audit}],
                    'provenance': provenance, 'detail': 'Approved source bindings became stale or unauthorized'}
        return {'status': 'completed', 'execution': 'live',
                'output': {'answer': '\n\n'.join(source['excerpt'] for source in sources) if sources else ABSTENTION,
                           'citations': [source['chunk_id'] for source in sources], 'tool_calls': []},
                'trace': [{'event': 'retrieval', 'limit': 6, 'chunk_ids': [source['chunk_id'] for source in sources],
                           'semantic': audit}], 'provenance': provenance,
                'detail': 'Real local embeddings and PostgreSQL hybrid retrieval; extractive output, no LLM generation'}
    except OntologyError as exc:
        return {'status': 'skipped', 'execution': 'live', 'output': None, 'trace': [],
                'provenance': provenance, 'detail': str(exc)}
    except Exception:
        return {'status': 'error', 'execution': 'live', 'output': None, 'trace': [],
                'provenance': provenance, 'detail': 'Adapter configuration, index, or local embedding failure'}


def write_json(path: Path, value) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


async def prepare(output: Path) -> None:
    dedicated_database()
    from sqlalchemy import select
    from .db import Chunk, Document, Session, Version
    from .domain import citation, source_rows
    from .extraction import extract
    from .migrate import migrate

    migrate()
    output.mkdir(parents=True, exist_ok=True)
    gateway = OllamaEmbeddings()
    try:
        for file in sorted((ROOT / 'fixtures' / 'manuals').glob('*/*.md')):
            raw, org = file.read_bytes(), file.parent.name
            content_hash = hashlib.sha256(raw).hexdigest()
            document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'ed-benchmark:{org}:{file.name}'))
            version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'{document_id}:{content_hash}'))
            sections = extract(file.name, raw)  # Known synthetic fixtures, never the upload sandbox.
            vectors = await gateway.embed([body for _, body in sections])
            with Session.begin() as db:
                existing = db.get(Document, document_id)
                if existing:
                    existing_version = db.scalar(select(Version).where(Version.document_id == document_id, Version.number == 1))
                    if not existing_version or existing_version.content_hash != content_hash or existing_version.provider != 'ollama' or (
                            existing_version.model != gateway.embedding_model or existing_version.dimensions != gateway.dimensions):
                        raise ValueError('Existing benchmark corpus differs; use a new dedicated benchmark DB')
                    continue
                db.add(Document(id=document_id, org=org, mode='LIVE', title=raw.decode().splitlines()[0].lstrip('# ')))
                db.flush()
                db.add(Version(id=version_id, document_id=document_id, number=1, filename=file.name,
                    content_hash=content_hash, content='', status='ready', provider=gateway.embedding_provider,
                    model=gateway.embedding_model, dimensions=gateway.dimensions))
                db.flush()
                for index, (location, body) in enumerate(sections):
                    db.add(Chunk(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{version_id}:{index}')),
                                 version_id=version_id, location=location, text=body, embedding=vectors[index]))
    finally:
        await gateway.aclose()
    concepts = json.loads((ROOT / 'fixtures' / 'ontology' / 'concepts.json').read_text(encoding='utf-8'))
    descriptors = json.loads((ROOT / 'fixtures' / 'ontology' / 'cases.json').read_text(encoding='utf-8'))
    specs, sources_by_org = {}, {}
    with Session() as db:
        for org in ('aurora', 'meridian'):
            rows = db.execute(source_rows(db, org, 'LIVE')).all()
            sources_by_org[org] = [citation(*row) for row in rows]
            terms, bindings = [], []
            for concept in concepts:
                if concept['org'] != org:
                    continue
                value = {key: concept[key] for key in ('id', 'name', 'description', 'synonyms')}
                value.update(name_certified=True, description_certified=True)
                terms.append({**value, 'sha256': term_digest(value)})
                for chunk, version, document in rows:
                    if document.title == concept['document'] and chunk.location == concept['location']:
                        bindings.append({'term_id': concept['id'], 'chunk_id': chunk.id, 'document_id': document.id,
                                         'document_version': version.number, 'content_sha256': version.content_hash})
            snapshot = {'schema_version': 1, 'application': 'evidence-desk', 'snapshot_id': f'{org}-manuals-v1',
                        'source': 'glossary', 'source_commit': 'synthetic-manuals-v1',
                        'scope': {'org': org, 'mode': 'LIVE'}, 'certified': True,
                        'approved_by': 'synthetic-fixture-review-v1', 'terms': terms, 'bindings': bindings}
            path = output / f'{org}.glossary.snapshot.json'
            digest = write_json(path, snapshot)
            specs[f'{org}:LIVE'] = {'path': str(path.resolve()), 'sha256': digest}
    cases = []
    for item in descriptors:
        sources = sources_by_org[item['org']]
        required = [source['chunk_id'] for source in sources if source['title'] == item['document'] and
                    source['location'] == item['location']]
        if not item['abstain'] and len(required) != 1:
            raise ValueError('Golden evidence must resolve to one original current chunk')
        cases.append({'id': item['id'], 'kind': 'rag', 'split': item['split'], 'prompt': item['prompt'],
                      'context': json.dumps(sources, ensure_ascii=False),
                      'expected': {'allowed_citations': [source['chunk_id'] for source in sources],
                                   'required_citations': required, 'answer_contains': item['answer_contains'],
                                   'abstain': item['abstain'], 'answer': ABSTENTION if item['abstain'] else ''}})
    write_json(output / 'dataset.json', cases)
    write_json(output / 'adapter-options.json', {'snapshots': specs,
        'scopes_by_case': {case['id']: case['org'] for case in descriptors},
        'embedding_model': gateway.embedding_model})
    print(json.dumps({'status': 'prepared', 'cases': len(cases), 'embedding_provider': 'ollama',
                      'embedding_model': gateway.embedding_model, 'dimensions': gateway.dimensions}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path, help='Index known fixtures and materialize separate golden cases')
    args = parser.parse_args()
    if args.prepare:
        asyncio.run(prepare(args.prepare.resolve()))
    else:
        try:
            raw = sys.stdin.buffer.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('Request too large')
            request = strict_json(raw)
            result = asyncio.run(observe(request))
        except Exception:
            result = {'status': 'error', 'execution': 'live', 'output': None, 'trace': [],
                      'detail': 'Invalid adapter request'}
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
