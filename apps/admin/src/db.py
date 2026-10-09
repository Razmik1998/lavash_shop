"""SQLAlchemy engine/session factory. Nothing above this module (other
than repository.py) should import sqlalchemy directly."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from config import Settings


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_business_timezone(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute(
            "SELECT set_config(%s, %s, false)",
            ("TimeZone", settings.business_timezone),
        )
        cursor.close()

    return sessionmaker(bind=engine, expire_on_commit=False)
