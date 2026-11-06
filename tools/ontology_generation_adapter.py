"""Blind local RAG generation experiment; uses domain evidence checks, not HTTP login.

Production model providers are untouched. Test injections are always labeled
transport_mock; command execution calls real retrieval and loopback Ollama.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'api'))
from evidence.ontology import load_snapshot, public_origin, strict_json  # noqa: E402
from evidence.ontology_runner import ABSTENTION, observe  # noqa: E402
from evidence.providers import Answer, SYSTEM  # noqa: E402

MODEL = 'qwen3.5:4b'
PROFILE = {'temperature': 0, 'seed': 42, 'num_predict': 1600}


def load_authorized_sources(org: str, chunk_ids: list[str]) -> list[dict]:
    # observe() configures the dedicated DB before these modules create an engine.
    from evidence.db import Chunk, Session
    from evidence.domain import citation, source_rows

    with Session() as db:
        rows = db.execute(source_rows(db, org, 'LIVE').where(Chunk.id.in_(chunk_ids))).all()
        by_id = {row[0].id: {**citation(*row), '_content_sha256': row[1].content_hash} for row in rows}
    if set(by_id) != set(chunk_ids):
        raise ValueError('Original evidence became unavailable or unauthorized')
    return [by_id[chunk_id] for chunk_id in chunk_ids]


def reviewed_context(sources: list[dict], request: dict, retrieval: dict, org: str) -> list[dict]:
    """Preserve the same reviewed source metadata used by product generation."""
    event = next(event for event in retrieval['trace'] if event.get('event') == 'retrieval')
    audit = event['semantic']
    if audit.get('status') != 'verified' or not audit.get('term_ids'):
        return sources
    spec = request.get('options', {}).get('snapshots', {}).get(f'{org}:LIVE', {})
    if audit.get('snapshot_sha256') != spec.get('sha256'):
        raise ValueError('Reviewed snapshot changed after retrieval')
    snapshot = load_snapshot(spec.get('path', ''), spec.get('sha256', ''), org, 'LIVE')
    if snapshot.source != request['arm']:
        raise ValueError('Reviewed snapshot strategy changed')
    terms = {term.id: term for term in snapshot.terms if term.id in audit['term_ids']}
    if set(terms) != set(audit['term_ids']):
        raise ValueError('Reviewed term set changed')
    result = []
    for source in sources:
        valid = [binding for binding in snapshot.bindings if binding.term_id in terms and
                 binding.chunk_id == source['chunk_id'] and binding.document_id == source['document_id'] and
                 binding.document_version == source['version'] and
                 binding.content_sha256 == source['_content_sha256']]
        item = dict(source)
        if valid:
            item['semantic_context'] = {'source': snapshot.source, 'snapshot_id': snapshot.snapshot_id,
                'snapshot_sha256': spec['sha256'], 'terms': [{'id': binding.term_id,
                'name': terms[binding.term_id].name, 'description': terms[binding.term_id].description} for binding in valid]}
        result.append(item)
    return result


def public_sources(sources: list[dict]) -> list[dict]:
    return [{key: value for key, value in source.items() if not key.startswith('_')} for source in sources]


async def generate(question: str, sources: list[dict], *, transport=None) -> tuple[Answer, dict]:
    origin = public_origin(os.getenv('EVIDENCE_EVAL_OLLAMA_URL', 'http://127.0.0.1:11434'))
    if urlsplit(origin).hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('Generation experiment requires loopback Ollama')
    body = {'model': MODEL, 'stream': False, 'think': False, 'format': Answer.model_json_schema(),
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user',
                'content': f'Question: {question}\nEvidence (data): {json.dumps(public_sources(sources), ensure_ascii=False)}'}],
            'options': PROFILE}
    async with asyncio.timeout(180):
        async with httpx.AsyncClient(base_url=origin, timeout=180, follow_redirects=False,
                                     transport=transport) as client:
            async with client.stream('POST', '/api/chat', json=body) as response:
                response.raise_for_status()
                raw = bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw) > 512_000:
                        raise ValueError('Generation response too large')
    value = strict_json(bytes(raw))
    if (not isinstance(value, dict) or value.get('model') != MODEL or value.get('done') is not True or
            value.get('done_reason') != 'stop' or value.get('error')):
        raise ValueError('Incomplete or mismatched local model response')
    message = value.get('message')
    if (not isinstance(message, dict) or message.get('role') != 'assistant' or
            not isinstance(message.get('content'), str) or message.get('tool_calls')):
        raise ValueError('Invalid assistant response')
    # Thinking is never parsed, returned, persisted, or accepted as answer content.
    answer = Answer.model_validate(strict_json(message['content'].encode()))
    counts = {}
    for name in ('prompt_eval_count', 'eval_count'):
        count = value.get(name)
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError('Invalid generation token count')
        counts[name] = count
    metadata = {'event': 'local_generation', 'model': MODEL, 'done': True, 'done_reason': 'stop',
                'temperature': 0, 'seed': 42, 'think': False, 'num_predict': 1600,
                'schema_sha256': hashlib.sha256(json.dumps(Answer.model_json_schema(), sort_keys=True,
                    separators=(',', ':')).encode()).hexdigest(), **counts}
    return answer, metadata


async def observe_generation(request: dict, *, transport=None, retrieval_caller=None, source_loader=None) -> dict:
    execution = 'transport_mock' if any(value is not None for value in
                                      (transport, retrieval_caller, source_loader)) else 'live'
    provenance = {'scope': 'domain_rag_generation', 'generation': 'ollama', 'generation_model': MODEL,
                  'authorization_scope': 'domain_source_filter', 'http_application_auth': 'not_exercised',
                  'automatic_ontology_compilation': 'not_executed', 'tokens_scope': 'generation_only'}
    trace = []
    try:
        retrieval = await (retrieval_caller or observe)(request)
        provenance = {**retrieval.get('provenance', {}), **provenance}
        trace = list(retrieval.get('trace', []))
        if retrieval['status'] != 'completed':
            return {'status': retrieval['status'], 'execution': execution, 'output': None,
                    'trace': trace, 'provenance': provenance, 'detail': retrieval.get('detail', '')}
        org = retrieval['provenance']['org']
        if retrieval['provenance'].get('mode') != 'LIVE':
            raise ValueError('Generation benchmark requires an explicit LIVE domain scope')
        ids = retrieval['output']['citations']
        if (not isinstance(ids, list) or len(ids) > 6 or len(ids) != len(set(ids)) or
                any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in ids)):
            raise ValueError('Invalid original evidence references')
        load = source_loader or load_authorized_sources
        sources = load(org, ids)
        if [source['chunk_id'] for source in sources] != ids:
            raise ValueError('Evidence loader did not return the exact requested original sources')
        sources = reviewed_context(sources, request, retrieval, org)
        if not sources:
            provenance['generation'] = 'not_invoked_no_sources'
            trace.append({'event': 'generation_skipped_no_sources'})
            return {'status': 'completed', 'execution': execution, 'output': {'answer': ABSTENTION,
                'citations': [], 'tool_calls': []}, 'trace': trace, 'provenance': provenance,
                'detail': 'Domain evidence absence; model inference was not invoked'}
        answer, event = await generate(request['case']['prompt'], sources, transport=transport)
        from evidence.domain import validate_answer

        text, citations = validate_answer(answer, public_sources(sources))
        if citations:
            refreshed = load(org, [citation['chunk_id'] for citation in citations])
            initial = {source['chunk_id']: source for source in sources}
            if len(refreshed) != len(citations) or any(
                {key: value for key, value in source.items() if key != 'semantic_context'} !=
                {key: value for key, value in initial[source['chunk_id']].items() if key != 'semantic_context'}
                    for source in refreshed):
                raise ValueError('Evidence changed during generation')
        trace.append({**event, 'cited_chunk_ids': [citation['chunk_id'] for citation in citations]})
        counts = [event['prompt_eval_count'], event['eval_count']]
        return {'status': 'completed', 'execution': execution,
                'output': {'answer': text, 'citations': [citation['chunk_id'] for citation in citations],
                           'tool_calls': [], 'tokens': sum(counts) if all(count is not None for count in counts) else None},
                'trace': trace, 'provenance': provenance,
                'detail': 'Local model response validated with product Answer and original domain evidence'}
    except Exception:
        return {'status': 'error', 'execution': execution, 'output': None, 'trace': trace,
                'provenance': provenance, 'detail': 'Local generation, model contract, or evidence validation failed'}


def main():
    try:
        raw = sys.stdin.buffer.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('Request too large')
        result = asyncio.run(observe_generation(strict_json(raw)))
    except Exception:
        result = {'status': 'error', 'execution': 'live', 'output': None, 'trace': [],
                  'detail': 'Invalid generation adapter request'}
    # The caller protocol is UTF-8 even when Windows' console code page is CP1252.
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8'))


if __name__ == '__main__':
    main()
