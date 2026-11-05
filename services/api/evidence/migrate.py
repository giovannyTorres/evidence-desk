"""Versioned, transactional migrations serialized by a PostgreSQL advisory lock."""
from sqlalchemy import text
from .db import Base, engine


def migrate():
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(683125)'))
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())'))
        current = conn.execute(text('SELECT max(version) FROM schema_migrations')).scalar()
        if not current:
            Base.metadata.create_all(conn)
            conn.execute(text("CREATE INDEX chunks_fts ON chunks USING gin(to_tsvector('english', text))"))
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (1)'))
        if not current or current < 2:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS mode varchar NOT NULL DEFAULT 'DEMO'"))
            conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS mode varchar NOT NULL DEFAULT 'DEMO'"))
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (2)'))


if __name__ == '__main__':
    migrate()
