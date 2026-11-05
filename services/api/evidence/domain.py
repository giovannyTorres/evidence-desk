import base64
import datetime as dt
import io
import json
import uuid
from pathlib import Path
from pypdf import PdfReader
from opentelemetry import trace
from sqlalchemy import delete, func, or_, select
from .config import settings
from .db import Chunk, Document, Job, Session, Version, now
from .providers import Answer, ModelGateway

FIXTURES = Path(__file__).resolve().parents[3] / 'fixtures'


def extract(filename: str, content: bytes) -> list[tuple[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError('Invalid PDF signature')
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError('PDF must be unencrypted and at most 100 pages')
        sections = [(f'Page {i+1}', page.extract_text() or '') for i, page in enumerate(reader.pages)]
    elif suffix in {'.txt', '.md'}:
        decoded = content.decode('utf-8')
        if '\x00' in decoded:
            raise ValueError('Binary content is not accepted')
        sections = []
        heading = 'Section 1'
        lines: list[str] = []
        for line in decoded.splitlines():
            if line.startswith('#'):
                if lines:
                    sections.append((heading, '\n'.join(lines)))
                heading, lines = line.lstrip('# ').strip()[:160], []
            else:
                lines.append(line)
        sections.append((heading, '\n'.join(lines)))
    else:
        raise ValueError('Only text PDF, UTF-8 TXT and Markdown are supported')
    result = [(loc, body[start:start+1200]) for loc, body in sections if body.strip()
              for start in range(0, len(body), 1000)]
    if not result:
        raise ValueError('No extractable text found; scanned PDFs need OCR outside this product')
    if len(result) > 400:
        raise ValueError('Document exceeds 400 text fragments')
    return result


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
    try:
        sections = extract(filename, base64.b64decode(data))
        vectors = None
        if config.mode == 'LIVE':
            if config.missing():
                raise ValueError('LIVE configuration incomplete')
            vectors = await ModelGateway(config).embed([body for _, body in sections])
        with Session.begin() as db:
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
            job = db.get(Job, job_id)
            assert job is not None
            job.state, job.lease_until = 'done', None
    except Exception as exc:
        # Content/config messages are safe. External errors are deliberately sanitized.
        error = str(exc)[:300] if isinstance(exc, (ValueError, UnicodeDecodeError)) else 'Processing failed; retry after checking provider availability'
        with Session.begin() as db:
            version, job = db.get(Version, version_id), db.get(Job, job_id)
            if version and job:
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
            Version.provider.is_(None)))).first()
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
