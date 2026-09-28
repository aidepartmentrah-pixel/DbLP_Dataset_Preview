import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://dblp:dblp@localhost/dblp"
)

# requirements.txt installs psycopg (v3), not psycopg2 - SQLAlchemy's
# "postgresql://" scheme defaults to psycopg2, so point it at v3 explicitly.
_ENGINE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(_ENGINE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
