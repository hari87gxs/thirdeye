import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

log = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auto_migrate():
    """Compare SQLAlchemy models against the live DB schema and
    ALTER TABLE to add any missing columns.  This is a lightweight
    forward-only migration that handles the common case of new
    columns being added to models without requiring Alembic.
    """
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() will handle brand-new tables

        db_columns = {col["name"] for col in inspector.get_columns(table.name)}
        model_columns = {col.name for col in table.columns}

        missing = model_columns - db_columns
        if not missing:
            continue

        log.warning("Table '%s' is missing columns: %s — running ALTER TABLE",
                     table.name, missing)

        with engine.begin() as conn:
            for col_name in missing:
                col = table.c[col_name]
                col_type = col.type.compile(engine.dialect)
                default_clause = ""
                if col.default is not None:
                    default_val = col.default.arg
                    if isinstance(default_val, str):
                        default_clause = f" DEFAULT '{default_val}'"
                    elif isinstance(default_val, (int, float)):
                        default_clause = f" DEFAULT {default_val}"
                    elif isinstance(default_val, bool):
                        default_clause = f" DEFAULT {int(default_val)}"
                stmt = f"ALTER TABLE {table.name} ADD COLUMN {col_name} {col_type}{default_clause}"
                log.info("  ➜ %s", stmt)
                conn.execute(text(stmt))


def init_db():
    """Create all tables and migrate any missing columns."""
    import models  # noqa: F401 — ensure models are registered with Base
    Base.metadata.create_all(bind=engine)
    _auto_migrate()
