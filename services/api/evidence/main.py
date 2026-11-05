import asyncio
import base64
import datetime as dt
import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from .auth import create_session, current_user
from .config import settings
from .db import Chunk, Conversation, Document, Job, LoginSession, Message, Session, Version, now
from .domain import citation, demo_answer, extract, retrieve, scenarios, validate_answer
from .providers import ModelGateway
from .seed import seed
from .telemetry import configure_tracing

log = logging.getLogger('evidence')
logging.basicConfig(level=logging.INFO, format='%(message)s')
tracer = trace.get_tracer('evidence-desk')
login_attempts: dict[str, list[float]] = defaultdict(list)


@asynccontextmanager
async def lifespan(app):
    seed()
    app.state.gateway = ModelGateway(settings())
    yield


app = FastAPI(title='Evidence Desk', version='1.0.0', lifespan=lifespan,
              description='Synthetic document evidence workspace. DEMO responses are fixtures, not model metrics.')
if settings().otel_enabled:
    configure_tracing()
    FastAPIInstrumentor.instrument_app(app)


@app.middleware('http')
async def correlation(request: Request, call_next):
    cid = str(uuid.uuid4())
    request.state.correlation_id = cid
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != settings().public_origin.rstrip('/'):
            return Response('Cross-origin writes are not accepted', status_code=403)
    start = time.monotonic()
    response = await call_next(request)
    response.headers['X-Correlation-ID'] = cid
    response.headers['X-Content-Type-Options'] = 'nosniff'
    log.info(json.dumps({'event': 'request', 'correlation_id': cid, 'method': request.method,
                        'path': request.url.path, 'status': response.status_code,
                        'duration_ms': round((time.monotonic()-start)*1000, 2)}))
    return response


@app.get('/api/openapi.json', include_in_schema=False)
def openapi_document():
    return app.openapi()


@app.get('/api/docs', include_in_schema=False)
def interactive_docs():
    return get_swagger_ui_html(openapi_url='/api/openapi.json', title='Evidence Desk API')


@app.get('/api/health')
def health():
    with Session() as db:
        db.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.get('/api/config')
def config():
    c = settings()
    return {'mode': c.mode, 'ready': not c.missing(), 'missing': c.missing(), 'provider': c.provider,
            'model': c.model, 'search': 'fixture evidence + lexical search' if c.mode == 'DEMO' else 'hybrid API embeddings + PostgreSQL full text'}


class Login(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


def user_data(user):
    return {'id': user.id, 'email': user.email, 'org': user.org, 'name': user.name}


@app.post('/api/auth/login')
def login(body: Login, request: Request, response: Response):
    key = request.client.host if request.client else 'unknown'
    recent = [t for t in login_attempts[key] if time.monotonic()-t < 60]
    login_attempts[key] = recent + [time.monotonic()]
    if len(recent) >= 20:
        raise HTTPException(429, 'Too many sign-in attempts; try again in a minute')
    token, user = create_session(body.email, body.password)
    response.set_cookie('evidence_session', token, httponly=True, samesite='strict',
                        secure=settings().cookie_secure, max_age=8*3600, path='/')
    return user_data(user)


@app.get('/api/me')
def me(user=Depends(current_user)):
    return user_data(user)


@app.post('/api/auth/logout')
def logout(request: Request, response: Response):
    token = request.cookies.get('evidence_session', '')
    with Session.begin() as db:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    response.delete_cookie('evidence_session', path='/')
    return {'ok': True}


def owned_document(db, document_id, user):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.org == user.org,
                                          Document.mode == settings().mode))
    if not doc:
        raise HTTPException(404, 'Document not found')
    return doc


def document_data(doc, version):
    return {'id': doc.id, 'title': doc.title, 'version': version.number, 'status': version.status,
            'filename': version.filename, 'error': version.error,
            'index': {'provider': version.provider, 'model': version.model, 'dimensions': version.dimensions}}


@app.get('/api/documents')
def documents(user=Depends(current_user)):
    with Session() as db:
        rows = db.execute(select(Document, Version).join(Version).where(Document.org == user.org,
            Document.mode == settings().mode, Version.number == Document.current_version).order_by(Document.title)).all()
        return [document_data(*row) for row in rows]


@app.post('/api/documents', status_code=201)
async def upload(file: UploadFile = File(...), title: str | None = Form(None),
                 document_id: str | None = Form(None), user=Depends(current_user)):
    data = await file.read(settings().max_upload_bytes + 1)
    if len(data) > settings().max_upload_bytes:
        raise HTTPException(413, 'File exceeds 5 MiB limit')
    name = (file.filename or 'document.txt').replace('\\', '/').split('/')[-1][:200]
    try:
        extract(name, data)
    except Exception as exc:
        raise HTTPException(422, str(exc)[:200] if isinstance(exc, ValueError) else 'Could not read this document') from None
    digest = hashlib.sha256(data).hexdigest()
    with Session.begin() as db:
        if document_id:
            doc = owned_document(db, document_id, user)
            db.refresh(doc, with_for_update=True)
            old = db.scalar(select(Version).where(Version.document_id == doc.id, Version.content_hash == digest))
            if old:
                return document_data(doc, old)
            doc.current_version += 1
        else:
            doc = Document(org=user.org, mode=settings().mode, title=(title or name)[:200])
            db.add(doc)
            db.flush()
        version = Version(document_id=doc.id, number=doc.current_version, filename=name,
                          content_hash=digest, content=base64.b64encode(data).decode())
        db.add(version)
        db.flush()
        db.add(Job(version_id=version.id))
        return document_data(doc, version)


@app.get('/api/documents/{document_id}/versions')
def versions(document_id: str, user=Depends(current_user)):
    with Session() as db:
        doc = owned_document(db, document_id, user)
        return [document_data(doc, v) for v in db.scalars(select(Version).where(Version.document_id == doc.id).order_by(Version.number))]


@app.get('/api/documents/{document_id}/file')
def download(document_id: str, version: int | None = None, user=Depends(current_user)):
    with Session() as db:
        doc = owned_document(db, document_id, user)
        v = db.scalar(select(Version).where(Version.document_id == doc.id, Version.number == (version or doc.current_version)))
        if not v:
            raise HTTPException(404, 'Version not found')
        return Response(base64.b64decode(v.content), media_type='application/octet-stream',
                        headers={'Content-Disposition': 'attachment; filename="document"'})


@app.delete('/api/documents/{document_id}')
def delete_document(document_id: str, user=Depends(current_user)):
    with Session.begin() as db:
        doc = owned_document(db, document_id, user)
        db.refresh(doc, with_for_update=True)
        # Remove historical citation links, preserving answer text with clear unavailable-source marker.
        for message in db.scalars(select(Message).join(Conversation).where(Conversation.org == user.org,
                                                                         Conversation.mode == settings().mode)):
            original = message.citations
            message.citations = [c for c in original if c['document_id'] != doc.id]
            if len(message.citations) != len(original):
                message.metadata_json = {**message.metadata_json, 'source_deleted': True}
        db.delete(doc)
    return {'ok': True}


@app.post('/api/documents/{document_id}/retry')
def retry(document_id: str, user=Depends(current_user)):
    with Session.begin() as db:
        doc = owned_document(db, document_id, user)
        version = db.scalar(select(Version).where(Version.document_id == doc.id, Version.number == doc.current_version).with_for_update())
        if version is None:
            raise HTTPException(404, 'Version not found')
        job = db.scalar(select(Job).where(Job.version_id == version.id))
        if job is None:
            raise HTTPException(404, 'Processing job not found')
        if version.status == 'processing':
            raise HTTPException(409, 'Document is already processing')
        job.state, job.lease_until, version.status, version.error = 'queued', None, 'queued', None
    return {'ok': True}


@app.get('/api/sources/{chunk_id}')
def source(chunk_id: str, user=Depends(current_user)):
    with Session() as db:
        row = db.execute(select(Chunk, Version, Document).join(Version, Chunk.version_id == Version.id).join(Document, Version.document_id == Document.id).where(Chunk.id == chunk_id,
            Document.org == user.org, Document.mode == settings().mode)).first()
        if not row:
            raise HTTPException(404, 'Source not found')
        return citation(*row)


@app.get('/api/search')
def search(q: str, user=Depends(current_user)):
    with Session() as db:
        rows = db.execute(select(Chunk, Version, Document).join(Version, Chunk.version_id == Version.id).join(Document, Version.document_id == Document.id).where(
            Document.org == user.org, Document.mode == settings().mode, Version.number == Document.current_version,
            Chunk.text.ilike(f'%{q[:200]}%')).limit(12)).all()
        return {'method': 'lexical substring search (no embeddings)', 'results': [citation(*row) for row in rows]}


@app.get('/api/scenarios')
def list_scenarios(user=Depends(current_user)):
    return [{'id': s['id'], 'question': s['question']} for s in scenarios()]


class NewConversation(BaseModel):
    title: str = Field(default='New evidence inquiry', min_length=1, max_length=160)


def owned_conversation(db, cid, user):
    convo = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id,
                                                Conversation.org == user.org, Conversation.mode == settings().mode))
    if not convo:
        raise HTTPException(404, 'Conversation not found')
    return convo


@app.post('/api/conversations', status_code=201)
def new_conversation(body: NewConversation, user=Depends(current_user)):
    with Session.begin() as db:
        convo = Conversation(user_id=user.id, org=user.org, mode=settings().mode, title=body.title)
        db.add(convo)
        db.flush()
        return {'id': convo.id, 'title': convo.title}


@app.get('/api/conversations')
def conversations(user=Depends(current_user)):
    with Session() as db:
        return [{'id': c.id, 'title': c.title} for c in db.scalars(select(Conversation).where(
            Conversation.user_id == user.id, Conversation.org == user.org, Conversation.mode == settings().mode))]


@app.get('/api/conversations/{conversation_id}')
def conversation(conversation_id: str, user=Depends(current_user)):
    with Session() as db:
        c = owned_conversation(db, conversation_id, user)
        messages = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created)).all()
        return {'id': c.id, 'title': c.title, 'messages': [{'id': m.id, 'role': m.role, 'content': m.content,
                'citations': m.citations, 'metadata': m.metadata_json} for m in messages]}


@app.post('/api/conversations/{conversation_id}/cancel')
def cancel(conversation_id: str, user=Depends(current_user)):
    with Session.begin() as db:
        c = owned_conversation(db, conversation_id, user)
        c.cancelled = True
    return {'ok': True}


class ChatRequest(BaseModel):
    scenario_id: str | None = None
    question: str | None = Field(default=None, max_length=2000)


def sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data)}\n\n'


@app.post('/api/conversations/{conversation_id}/messages')
async def chat(conversation_id: str, body: ChatRequest, request: Request, user=Depends(current_user)):
    config = settings()
    if config.mode == 'DEMO':
        scenario = next((s for s in scenarios() if s['id'] == body.scenario_id), None)
        if not scenario:
            raise HTTPException(422, 'Free-form interpretation requires LIVE. Choose a DEMO example question.')
        question = scenario['question']
    else:
        if config.missing():
            raise HTTPException(503, 'LIVE configuration incomplete; see mode status')
        question = (body.question or '').strip()
        if not question:
            raise HTTPException(422, 'Enter a question')
    with Session.begin() as db:
        c = owned_conversation(db, conversation_id, user)
        db.refresh(c, with_for_update=True)
        if c.busy and c.lease_until and c.lease_until > now():
            raise HTTPException(409, 'An answer is already running')
        c.busy, c.cancelled, c.lease_until = True, False, now() + dt.timedelta(minutes=2)
        db.add(Message(conversation_id=c.id, role='user', content=question))

    async def events():
        task = None
        try:
            with tracer.start_as_current_span('rag.answer'):
                if config.mode == 'DEMO':
                    answer_text, citations = demo_answer(body.scenario_id, user.org)
                else:
                    async def generate_answer():
                        gateway = request.app.state.gateway
                        sources = await retrieve(question, user.org, gateway)
                        if not sources:
                            return 'I could not find enough evidence in the authorized documents to answer this question.', []
                        result = await gateway.generate(question, json.dumps(sources))
                        return validate_answer(result, sources)
                    task = asyncio.create_task(generate_answer())
                    while not task.done():
                        with Session() as db:
                            c = db.get(Conversation, conversation_id)
                            if not c or c.cancelled or await request.is_disconnected():
                                task.cancel()
                                raise asyncio.CancelledError
                        yield ': keep-alive\n\n'
                        await asyncio.wait({task}, timeout=0.25)
                    answer_text, citations = await task
                # Do not expose raw structured model output before reference validation.
                for offset in range(0, len(answer_text), 36):
                    with Session() as db:
                        c = db.get(Conversation, conversation_id)
                        if c.cancelled or await request.is_disconnected():
                            raise asyncio.CancelledError
                    yield sse('token', {'text': answer_text[offset:offset+36]})
                    await asyncio.sleep(0)
                with Session.begin() as db:
                    # Recheck source existence/authorization against concurrent deletion.
                    ids = [s['chunk_id'] for s in citations]
                    list(db.scalars(select(Document).where(Document.id.in_([s['document_id'] for s in citations])).with_for_update(read=True)))
                    authorized = set(db.scalars(select(Chunk.id).join(Version).join(Document).where(
                        Chunk.id.in_(ids), Document.org == user.org, Document.mode == config.mode)))
                    if set(ids) != authorized:
                        raise ValueError('Evidence changed while answering. Please retry.')
                    m = Message(conversation_id=conversation_id, role='assistant', content=answer_text,
                                citations=citations, metadata_json={'mode': config.mode, 'fixture': config.mode == 'DEMO',
                                'provider': config.provider if config.mode == 'LIVE' else None,
                                'model': config.model if config.mode == 'LIVE' else None})
                    db.add(m)
                    db.flush()
                    message_id = m.id
                yield sse('citations', {'citations': citations})
                yield sse('done', {'message_id': message_id})
        except asyncio.CancelledError:
            if task:
                task.cancel()
            with Session.begin() as db:
                db.add(Message(conversation_id=conversation_id, role='system', content='Answer cancelled.', metadata_json={'cancelled': True}))
            yield sse('cancelled', {'message': 'Answer cancelled'})
        except Exception:
            with Session.begin() as db:
                db.add(Message(conversation_id=conversation_id, role='system', content='The answer could not be completed. Retry or check LIVE configuration.', metadata_json={'error': True}))
            yield sse('error', {'message': 'The answer could not be completed. Retry or check LIVE configuration.', 'correlation_id': request.state.correlation_id})
        finally:
            with Session.begin() as db:
                c = db.get(Conversation, conversation_id)
                if c:
                    c.busy, c.lease_until = False, None
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
