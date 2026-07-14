"""Database engine management and DDL tooling for MAIC-DB.

Responsibilities:

* provide a :class:`~sqlalchemy.engine.Engine` factory (default: in-memory SQLite),
* :func:`create_all` — instantiate the full schema on an engine,
* :func:`render_ddl` — render the schema to reviewable plain SQL (the checked-in
  ``schema.sql`` is produced this way), and :func:`dump_schema_sql` to write it,
* two small console-script entry points (``maicdb-init-db``, ``maicdb-dump-schema``)
  wired in ``pyproject.toml``.

``Base`` is defined in :mod:`maicdb.models` (so importing that module registers
every table) and re-exported here for convenience.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects import sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from maicdb.models import ALL_TABLES, Base

__all__ = [
    "Base",
    "make_engine",
    "create_all",
    "render_ddl",
    "dump_schema_sql",
    "SCHEMA_PATH",
    "init_db_cli",
    "dump_schema_cli",
]

#: Location of the checked-in DDL dump, relative to this package.
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def make_engine(url: str = "sqlite:///:memory:", echo: bool = False) -> Engine:
    """Create a SQLAlchemy ``Engine``.

    Defaults to an in-memory SQLite database, which is ideal for tests and
    ephemeral validation. Pass a file URL (``sqlite:///path/to/maicdb.db``)
    for a persistent database.
    """
    return create_engine(url, future=True, echo=echo)


def create_all(engine: Engine) -> None:
    """Create every MAIC-DB table on *engine* (idempotent via ``checkfirst``)."""
    Base.metadata.create_all(engine)


def render_ddl() -> str:
    """Render the full schema as SQLite DDL (``CREATE TABLE`` + ``CREATE INDEX``).

    Tables are emitted in dependency order (``metadata.sorted_tables``); each
    table is followed by its ``CREATE INDEX`` statements. Enum columns render
    as ``VARCHAR`` with ``CHECK`` constraints (SQLite has no native ENUM).
    """
    dialect = sqlite.dialect()
    chunks: list[str] = []
    for table in Base.metadata.sorted_tables:
        chunks.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            chunks.append(
                str(CreateIndex(index).compile(dialect=dialect)).strip()
            )
    return "\n\n".join(chunks) + "\n"


def dump_schema_sql(path: Path | str | None = None) -> Path:
    """Write :func:`render_ddl` to *path* (default: the package ``schema.sql``).

    Returns the resolved path written to.
    """
    target = Path(path) if path is not None else SCHEMA_PATH
    target.write_text(render_ddl(), encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# Console-script entry points
# --------------------------------------------------------------------------- #
def init_db_cli(argv: list[str] | None = None) -> int:
    """``maicdb-init-db`` — create the MAIC-DB schema on a SQLite database."""
    parser = argparse.ArgumentParser(
        prog="maicdb-init-db",
        description="Create the MAIC-DB schema on a SQLite database.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="sqlite:///maicdb.db",
        help="SQLAlchemy database URL (default: ./maicdb.db)",
    )
    args = parser.parse_args(argv)
    engine = make_engine(args.url)
    create_all(engine)
    print(f"[maicdb] schema created on {args.url}")
    # Report table inventory for confirmation.
    names = sorted(t.name for t in ALL_TABLES)
    print(f"[maicdb] {len(names)} tables: {', '.join(names)}")
    return 0


def dump_schema_cli(argv: list[str] | None = None) -> int:
    """``maicdb-dump-schema`` — regenerate the ``schema.sql`` DDL dump."""
    parser = argparse.ArgumentParser(
        prog="maicdb-dump-schema",
        description="Render the MAIC-DB schema to a SQL DDL file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(SCHEMA_PATH),
        help=f"output path (default: {SCHEMA_PATH})",
    )
    args = parser.parse_args(argv)
    written = dump_schema_sql(args.output)
    print(f"[maicdb] DDL written to {written}")
    return 0
