"""Integration-test fixtures against a real disposable PostgreSQL
database (see skills/testing/database-tests.md)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base
from repository import (
    PosSessionRepository,
    ProductRepository,
    SaleRepository,
    UserRepository,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://shop_admin:changeme@localhost:5432/shop_admin_test",
)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def user_repository(session_factory: sessionmaker[Session]) -> UserRepository:
    return UserRepository(session_factory)


@pytest.fixture
def product_repository(
    session_factory: sessionmaker[Session],
) -> ProductRepository:
    return ProductRepository(session_factory)


@pytest.fixture
def pos_session_repository(
    session_factory: sessionmaker[Session],
) -> PosSessionRepository:
    return PosSessionRepository(session_factory)


@pytest.fixture
def sale_repository(session_factory: sessionmaker[Session]) -> SaleRepository:
    return SaleRepository(session_factory)
