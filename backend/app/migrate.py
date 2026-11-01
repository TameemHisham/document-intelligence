"""Minimal forward-only schema sync: create tables, add missing columns, set up pgvector.

Good enough for an MVP with additive changes; switch to Alembic once columns get renamed/dropped.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db import Base

log = logging.getLogger(__name__)


def sync_schema(engine: Engine, pgvector: bool) -> None:
    if pgvector:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
                default = col.default.arg if col.default is not None and col.default.is_scalar else None
                if default is not None:
                    lit = f"'{default}'" if isinstance(default, str) else str(int(default) if isinstance(default, bool) else default)
                    ddl += f" DEFAULT {lit}"
                log.info("migrate: %s", ddl)
                conn.execute(text(ddl))

        if pgvector:  # approximate-NN indexes; exact search is fine below ~100k rows, HNSW keeps it fast after
            conn.execute(text("CREATE INDEX IF NOT EXISTS chunks_vec_hnsw ON chunks USING hnsw (vec vector_cosine_ops)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS image_vectors_vec_hnsw ON image_vectors USING hnsw (vec vector_cosine_ops)"))
