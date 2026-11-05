import base64
import datetime as dt
import asyncio
import os
import subprocess
import sys
import threading
import json
import uuid
from pathlib import Path
from opentelemetry import trace
from sqlalchemy import delete, func, or_, select
from .config import settings
from .db import Chunk, Document, Job, Session, Version, now
from .providers import Answer, ModelGateway

FIXTURES = Path(__file__).resolve().parents[3] / 'fixtures'
PARSER_SLOTS = threading.BoundedSemaphore(2)


def validate_upload(filename: str, content: bytes) -> None:
    if len(content) > settings().max_upload_bytes:
        raise ValueError('File exceeds 5 MiB limit')
    # Simple format checks retain actionable errors before the sandboxed parser.
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.pdf', '.txt', '.md'}:
        raise ValueError('Only text PDF, UTF-8 TXT and Markdown are supported')
    if suffix == '.pdf' and not content.startswith(b'%PDF-'):
        raise ValueError('Invalid PDF signature')
    if suffix != '.pdf':
        try:
            decoded = content.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('Text documents must use UTF-8') from None
        if '\x00' in decoded or not decoded.strip():
            raise ValueError('Document must contain nonempty UTF-8 text')


def extract(filename: str, content: bytes) -> list[tuple[str, str]]:
    validate_upload(filename, content)
    environment = {key: value for key, value in os.environ.items() if key in {'PATH', 'PYTHONPATH', 'SYSTEMROOT'}}
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    if not PARSER_SLOTS.acquire(timeout=10):
        raise ValueError('Document parser is busy; retry the processing job')
    try:
        result = subprocess.run([sys.executable, '-m', 'evidence.extraction'],
            input=json.dumps({'filename': filename, 'data': base64.b64encode(content).decode()}).encode(),
            capture_output=True, timeout=10, env=environment, check=False)
        decoded = json.loads(result.stdout)
        if result.returncode or not isinstance(decoded, list):
            raise ValueError('Document could not be safely extracted; use an unencrypted text PDF, UTF-8 TXT or Markdown.')
        return [(location, body) for location, body in decoded]
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        raise ValueError('Document extraction exceeded resource limits or returned no text') from None
    finally:
        PARSER_SLOTS.release()


@trace.get_tracer("evidence-desk").start_as_current_span("document.process")
async def process_one() -> bool:
    config = settings()
    with Session.begin() as db:
        job = db.scalar(select(Job).join(Version).join(Document).where(Document.mode == config.mode,
            or_(Job.state == 'queued', (Job.state == 'processing') & (Job.lease_until < now())))
            .order_by(Job.id).with_for_update(skip_locked=True))
        if not job:
            return False
        job.state = 'processing'
        job.attempts += 1
        job.lease_until = now() + dt.timedelta(minutes=5)
        version = db.get(Version, job.version_id)
        assert version is not None
        version.status = 'processing'
        job_id, version_id, filename, data = job.id, version.id, version.filename, version.content
        attempt, document_id = job.attempts, version.document_id
    try:
        sections = await asyncio.to_thread(extract, filename, base64.b64decode(data))
        vectors = None
        if config.mode == 'LIVE':
            if config.missing():
                raise ValueError('LIVE configuration incomplete')
            gateway = ModelGateway(config)
            try:
                vectors = await gateway.embed([body for _, body in sections])
            finally:
                await gateway.aclose()
        with Session.begin() as db:
            document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            # A lease can be reclaimed while an earlier slow process is still alive.
            # Its attempt number is a fencing token: stale results must not commit.
            if not document or not job or job.attempts != attempt or job.state != 'processing':
                return True
            version = db.get(Version, version_id)
            if not version:  # deleted during processing
                return True
            db.execute(delete(Chunk).where(Chunk.version_id == version_id))
            for i, (location, body) in enumerate(sections):
                db.add(Chunk(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{version_id}:{i}")), version_id=version_id, location=location, text=body,
                             embedding=vectors[i] if vectors else None))
            version.status, version.error = 'ready', None
            if vectors:
                version.provider, version.model, version.dimensions = 'openai', config.embedding_model, config.embedding_dimensions
            job.state, job.lease_until = 'done', None
    except Exception as exc:
        # Content/config messages are safe. External errors are deliberately sanitized.
        error = str(exc)[:300] if isinstance(exc, (ValueError, UnicodeDecodeError)) else 'Processing failed; retry after checking provider availability'
        with Session.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            version = db.get(Version, version_id)
            if version and job and job.attempts == attempt and job.state == 'processing':
                version.status, version.error, job.state = 'error', error, 'failed'
    return True


def citation(chunk: Chunk, version: Version, document: Document) -> dict:
    return {'chunk_id': chunk.id, 'document_id': document.id, 'version': version.number,
            'location': chunk.location, 'excerpt': chunk.text, 'title': document.title}


def source_rows(db, org: str, mode: str):
    return select(Chunk, Version, Document).join(Version, Chunk.version_id == Version.id).join(Document,
        Version.document_id == Document.id).where(Document.org == org, Document.mode == mode,
        Version.status == 'ready', Version.number == Document.current_version)


def validate_answer(answer: Answer, sources: list[dict]) -> tuple[str, list[dict]]:
    allowed = {c['chunk_id']: c for c in sources}
    if answer.abstain or not answer.chunk_ids:
        return 'I could not find enough evidence in the authorized documents to answer this question.', []
    if any(chunk_id not in allowed for chunk_id in answer.chunk_ids):
        raise ValueError('Model returned an invalid evidence reference')
    return answer.text, [allowed[cid] for cid in dict.fromkeys(answer.chunk_ids)]


@trace.get_tracer("evidence-desk").start_as_current_span("rag.retrieve")
async def retrieve(question: str, org: str, gateway: ModelGateway) -> list[dict]:
    config = settings()
    vector = (await gateway.embed([question]))[0]
    with Session() as db:
        base = source_rows(db, org, 'LIVE')
        incompatible = db.execute(base.where(or_(Version.provider != 'openai',
            Version.model != config.embedding_model, Version.dimensions != len(vector),
            Version.provider.is_(None), Version.model.is_(None), Version.dimensions.is_(None)))).first()
        if incompatible:
            raise ValueError('An index is incompatible with the configured embeddings; reindex before querying')
        # Both candidates are filtered by tenant/mode/current-version before rank fusion.
        lexical = db.execute(base.where(func.to_tsvector('english', Chunk.text).op('@@')(
            func.plainto_tsquery('english', question))).order_by(func.ts_rank_cd(
            func.to_tsvector('english', Chunk.text), func.plainto_tsquery('english', question)).desc()).limit(12)).all()
        semantic = db.execute(base.where(Chunk.embedding.is_not(None)).order_by(
            Chunk.embedding.cosine_distance(vector)).limit(12)).all()
        ranks: dict[str, float] = {}
        rows = {}
        for candidates in (lexical, semantic):
            for rank, row in enumerate(candidates):
                ranks[row[0].id] = ranks.get(row[0].id, 0) + 1 / (60 + rank)
                rows[row[0].id] = row
        return [citation(*rows[cid]) for cid in sorted(ranks, key=lambda c: ranks[c], reverse=True)[:6]]


def scenarios() -> list[dict]:
    return json.loads((FIXTURES / 'scenarios.json').read_text())


def demo_answer(scenario_id: str, org: str) -> tuple[str, list[dict]]:
    scenario = next((s for s in scenarios() if s['id'] == scenario_id), None)
    if not scenario:
        raise ValueError('Choose a listed DEMO scenario')
    if scenario['document'] is None:
        return 'I could not find enough evidence in the authorized documents to answer this question.', []
    with Session() as db:
        rows = db.execute(source_rows(db, org, 'DEMO').where(Document.title == scenario['document'],
                                                            Chunk.location == scenario['location'], Version.content_hash == scenario['evidence_hash'])).all()
        if not rows:
            return 'The sample evidence is not available in this organization. I cannot support an answer.', []
        sources = [citation(*row) for row in rows]
        return scenario['answer'], sources[:1]
