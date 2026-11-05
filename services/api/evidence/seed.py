import base64
import hashlib
from sqlalchemy import select, text
from .auth import hash_password
from .config import settings
from .db import Document, Job, Session, User, Version
from .domain import FIXTURES
from .migrate import migrate


def seed():
    migrate()
    with Session.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(683126)'))
        for org, name in [('aurora', 'Aurora Cooperative'), ('meridian', 'Meridian Studio')]:
            email = f'analyst@{org}.example'
            if settings().mode == 'DEMO' and settings().demo_login_enabled and not db.scalar(select(User).where(User.email == email)):
                db.add(User(org=org, email=email, name=name, password_hash=hash_password('demo-evidence')))
            if settings().mode != 'DEMO':
                continue
            for file in sorted((FIXTURES / 'manuals' / org).glob('*.md')):
                title = file.read_text().splitlines()[0].lstrip('# ')
                if db.scalar(select(Document).where(Document.org == org, Document.mode == 'DEMO', Document.title == title)):
                    continue
                doc = Document(org=org, mode='DEMO', title=title)
                db.add(doc)
                db.flush()
                data = file.read_bytes()
                version = Version(document_id=doc.id, number=1, filename=file.name,
                    content_hash=hashlib.sha256(data).hexdigest(), content=base64.b64encode(data).decode())
                db.add(version)
                db.flush()
                db.add(Job(version_id=version.id))


if __name__ == '__main__':
    seed()
