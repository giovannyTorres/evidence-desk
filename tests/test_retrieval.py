import uuid
import pytest
from sqlalchemy import delete
from evidence.config import settings
from evidence.db import Chunk, Document, Session, Version
from evidence.domain import retrieve


class FixtureEmbeddings:
    async def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


async def test_real_pgvector_hybrid_filters_tenant_and_rejects_incompatible_index(monkeypatch):
    monkeypatch.setattr(settings(), 'embedding_dimensions', 3)
    ids=[]
    try:
        with Session.begin() as db:
            for org in ['aurora','meridian']:
                doc=Document(org=org,mode='LIVE',title='synthetic vector evidence '+uuid.uuid4().hex)
                db.add(doc)
                db.flush()
                ids.append(doc.id)
                version=Version(document_id=doc.id,number=1,filename='live.txt',content_hash='synthetic',content='',status='ready',provider='openai',model=settings().embedding_model,dimensions=3)
                db.add(version)
                db.flush()
                db.add(Chunk(version_id=version.id,location='Section 1',text=f'{org} unique synthetic allowance',embedding=[1.0,0.0,0.0]))
        results=await retrieve('allowance', 'aurora', FixtureEmbeddings())
        assert results and all(c['document_id']==ids[0] for c in results)
        monkeypatch.setattr(settings(),'embedding_model','different-model')
        with pytest.raises(ValueError,match='incompatible'):
            await retrieve('allowance', 'aurora', FixtureEmbeddings())
    finally:
        with Session.begin() as db:
            db.execute(delete(Document).where(Document.id.in_(ids)))
