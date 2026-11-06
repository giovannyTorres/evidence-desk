"""Optional reviewed semantic context. Only original authorized chunks are evidence.

NVIDIA is accessed through its public GET API, never its trusted internal backend.
The pinned application snapshot is the allowlist; a remote certification flag alone
does not authorize a term, tenant, document, or action.
"""
from dataclasses import dataclass, field
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import Settings


class OntologyError(ValueError):
    """Safe, bounded failure; provider bodies and credentials never escape."""


def term_digest(value: dict) -> str:
    fields = {key: value[key] for key in (
        'id', 'name', 'description', 'name_certified', 'description_certified')}
    fields['synonyms'] = sorted(set(value.get('synonyms') or []))
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Term(Strict):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=3000)
    synonyms: list[str] = Field(default_factory=list, max_length=30)
    name_certified: bool = Field(strict=True)
    description_certified: bool = Field(strict=True)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def reviewed(self):
        if not self.name_certified or not self.description_certified:
            raise ValueError('Both term fields must be certified')
        if any(not word.strip() or len(word) > 160 for word in self.synonyms):
            raise ValueError('Invalid synonym')
        if term_digest(self.model_dump()) != self.sha256:
            raise ValueError('Term digest mismatch')
        return self


class Scope(Strict):
    org: str = Field(min_length=1, max_length=100)
    mode: Literal['DEMO', 'LIVE']


class Binding(Strict):
    term_id: str
    chunk_id: str
    document_id: str
    document_version: int = Field(ge=1, strict=True)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class Snapshot(Strict):
    schema_version: Literal[1]
    application: Literal['evidence-desk']
    snapshot_id: str = Field(min_length=1, max_length=160)
    source: Literal['glossary', 'auto_ontology']
    source_commit: str = Field(min_length=1, max_length=200)
    scope: Scope
    certified: bool = Field(strict=True)
    approved_by: str = Field(min_length=1, max_length=160)
    terms: list[Term] = Field(max_length=100)
    bindings: list[Binding] = Field(max_length=500)

    @model_validator(mode='after')
    def approved(self):
        ids = [term.id for term in self.terms]
        if not self.certified or len(ids) != len(set(ids)):
            raise ValueError('An application-approved snapshot with unique terms is required')
        if any(binding.term_id not in ids for binding in self.bindings):
            raise ValueError('Unknown binding term')
        return self


def strict_json(content: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid JSON number')))


def load_snapshot(path: str, sha256: str, org: str, mode: str) -> Snapshot:
    try:
        file = Path(path)
        if file.stat().st_size > 512_000:
            raise ValueError('Snapshot exceeds size limit')
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha256:
            raise ValueError('Snapshot digest mismatch')
        snapshot = Snapshot.model_validate(strict_json(raw))
        if snapshot.scope.org != org or snapshot.scope.mode != mode:
            raise ValueError('Snapshot scope mismatch')
        return snapshot
    except (OSError, ValueError, TypeError, KeyError):
        raise OntologyError('Reviewed ontology snapshot is unavailable or invalid') from None


def _phrase(value: str) -> str:
    return ' '.join(re.findall(r'\w+', value.casefold()))


def matched_terms(snapshot: Snapshot, question: str) -> list[Term]:
    question = ' ' + _phrase(question) + ' '
    return [term for term in snapshot.terms if any(
        ' ' + _phrase(name) + ' ' in question for name in [term.name, *term.synonyms])][:6]


def public_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in {'', '/'} or not parsed.hostname or
            (parsed.scheme != 'https' and not (parsed.scheme == 'http' and
             parsed.hostname in {'localhost', '127.0.0.1', '::1'}))):
        raise OntologyError('Auto Ontology requires an HTTPS origin or loopback HTTP')
    return value.rstrip('/')


def connection_for(config: Settings, org: str, mode: str) -> tuple[str, str]:
    if config.auto_ontology_connections:
        connection = config.auto_ontology_connections.get(f'{org}:{mode}', {})
        name = connection.get('token_env', '')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', name):
            raise OntologyError('Auto Ontology scoped token reference is not configured')
        token = os.getenv(name, '')
        if not connection.get('url') or not token:
            raise OntologyError('Auto Ontology scoped connection is not configured')
        return connection['url'], token
    if not config.auto_ontology_url:
        raise OntologyError('Auto Ontology public API is not configured')
    return config.auto_ontology_url, config.auto_ontology_api_token


class AutoOntologyClient:
    def __init__(self, origin: str, token: str, timeout: float = 5,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.origin = public_origin(origin)
        self.requests = 0
        self.client = httpx.AsyncClient(base_url=self.origin, timeout=timeout,
            follow_redirects=False, headers={'x-api-key': token} if token else {}, transport=transport)

    async def aclose(self):
        await self.client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        self.requests += 1
        try:
            async with self.client.stream('GET', path, params=params) as response:
                response.raise_for_status()
                content = bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content) > 512_000:
                        raise ValueError('Response too large')
                value = strict_json(bytes(content))
                if not isinstance(value, dict):
                    raise ValueError('Invalid envelope')
                return value
        except (httpx.HTTPError, ValueError, TypeError):
            raise OntologyError('Auto Ontology request failed or returned an invalid contract') from None

    async def verify(self, term: Term) -> None:
        found = False
        for skip in range(0, 150, 50):
            page = await self._get('/api/terms', {'query': term.name, 'skip': skip, 'limit': 50})
            rows, total = page.get('terms'), page.get('total')
            if not isinstance(rows, list) or len(rows) > 50 or type(total) is not int or total < 0:
                raise OntologyError('Auto Ontology returned an invalid terms page')
            if any(isinstance(row, dict) and row.get('id') == term.id for row in rows):
                found = True
                break
            if skip + len(rows) >= total or not rows:
                break
        if not found:
            raise OntologyError('Approved term is absent from Auto Ontology')
        envelope = await self._get('/api/terms/' + quote(term.id, safe=''))
        try:
            data = envelope['data']
            fields = {key: data[key] for key in (
                'id', 'name', 'description', 'name_certified', 'description_certified')}
            fields['synonyms'] = data.get('synonyms') or []
            remote = Term(**fields, sha256=term_digest(fields))
            if remote.id != term.id or remote.sha256 != term.sha256:
                raise ValueError('Reviewed term changed')
        except (ValueError, TypeError, KeyError):
            raise OntologyError('Auto Ontology term differs from the application-approved revision') from None


@dataclass
class SemanticContext:
    terms: list[Term] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    audit: dict = field(default_factory=lambda: {'strategy': 'off', 'status': 'disabled'})


async def resolve_context(question: str, org: str, mode: str, config: Settings,
                          strategy: str | None = None, *, strict: bool = False,
                          transport: httpx.AsyncBaseTransport | None = None) -> SemanticContext:
    strategy = strategy or config.ontology_mode
    context = SemanticContext(audit={'strategy': strategy, 'status': 'disabled'})
    if strategy in {'off', 'baseline'} or mode != 'LIVE' or config.mode != 'LIVE':
        return context
    if strategy not in {'glossary', 'auto_ontology'}:
        raise OntologyError('Unknown semantic strategy')
    try:
        spec = config.ontology_snapshots.get(f'{org}:{mode}', {})
        snapshot = load_snapshot(spec.get('path', ''), spec.get('sha256', ''), org, mode)
        if snapshot.source != strategy:
            raise OntologyError('Snapshot source does not match the selected strategy')
        selected = matched_terms(snapshot, question)
        if strategy == 'auto_ontology':
            origin, token = connection_for(config, org, mode)
            client = AutoOntologyClient(origin, token, config.ontology_timeout, transport)
            try:
                # One wall-clock budget for all pages/terms, including slow-drip bodies.
                async with asyncio.timeout(config.ontology_timeout):
                    for term in selected:
                        await client.verify(term)
                    if not selected:
                        await client._get('/api/terms', {'skip': 0, 'limit': 1})
            except TimeoutError:
                raise OntologyError('Auto Ontology exceeded the total request budget') from None
            finally:
                await client.aclose()
            context.audit['remote_requests'] = client.requests
        selected_ids = {term.id for term in selected}
        context.terms = selected
        context.bindings = [binding for binding in snapshot.bindings if binding.term_id in selected_ids]
        context.audit = {'strategy': strategy, 'status': 'verified', 'snapshot_id': snapshot.snapshot_id,
                         'snapshot_sha256': spec['sha256'], 'source_commit': snapshot.source_commit,
                         'term_ids': sorted(selected_ids), 'matched_terms': len(selected),
                         **({'remote_requests': context.audit['remote_requests']}
                            if 'remote_requests' in context.audit else {})}
    except OntologyError:
        if strict:
            raise
        context.audit['status'] = 'unavailable_baseline_fallback'
    return context
