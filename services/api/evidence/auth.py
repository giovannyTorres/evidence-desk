import datetime as dt
import hashlib
import hmac
import secrets
from fastapi import Cookie, HTTPException
from sqlalchemy import select
from .config import settings
from .db import LoginSession, Session, User, now


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    return f'{salt}${digest}'


def verify(password: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(password, hashed.split('$')[0]), hashed)


def current_user(evidence_session: str | None = Cookie(default=None)) -> User:
    if not evidence_session:
        raise HTTPException(401, 'Sign in to continue')
    digest = hashlib.sha256(evidence_session.encode()).hexdigest()
    with Session() as db:
        session = db.get(LoginSession, digest)
        if not session or session.expires < now() or session.mode != settings().mode:
            raise HTTPException(401, 'Session expired')
        user = db.get(User, session.user_id)
        if not user or user.mode != settings().mode:
            raise HTTPException(401, 'Session expired')
        return user


def create_session(email: str, password: str) -> tuple[str, User]:
    with Session() as db:
        user = db.scalar(select(User).where(User.email == email))
        if not user or user.mode != settings().mode or not verify(password, user.password_hash):
            raise HTTPException(401, 'Invalid email or password')
        token = secrets.token_urlsafe(32)
        db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, mode=settings().mode,
                            expires=now() + dt.timedelta(hours=8)))
        db.commit()
        return token, user
