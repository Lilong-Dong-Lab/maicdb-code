"""Shared pytest fixtures for MAIC-DB schema tests.

Each test gets a fresh in-memory SQLite database with the full schema applied.
``StaticPool`` pins a single connection so the in-memory database persists
across the session's connection checkouts.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from maicdb.models import Base


@pytest.fixture()
def engine() -> Engine:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine: Engine) -> Session:
    with Session(engine) as s:
        yield s
