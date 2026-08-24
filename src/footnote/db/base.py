import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
# SQL_ECHO=1 logs every statement — handy while shaping the schema, noisy in tests.
engine = create_engine(DATABASE_URL, echo=os.getenv("SQL_ECHO") == "1")
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase): pass


def init_db() -> None:
    from footnote.db import models  # noqa: F401 — import registers models on Base.metadata

    with engine.begin() as conn:
        # vector(384) columns don't exist as a type until the extension is installed,
        # so this has to land before create_all.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
