from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from agent_core_platform_api.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_database() -> None:
    from agent_core_platform_api import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def run_database_migrations() -> None:
    alembic_config_path = os.getenv("AGENT_CORE_ALEMBIC_CONFIG")
    if not alembic_config_path:
        raise RuntimeError("AGENT_CORE_ALEMBIC_CONFIG must point at the starter API alembic.ini file.")

    from alembic import command
    from alembic.config import Config

    config_path = Path(alembic_config_path).resolve()
    config = Config(str(config_path))
    config.set_main_option("script_location", str((config_path.parent / "migrations").resolve()))
    # Alembic stores this value through ConfigParser, which treats "%" as
    # interpolation syntax. Escape it here without changing the runtime URL
    # used by SQLAlchemy itself.
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def reset_database_state() -> None:
    get_engine.cache_clear()
    get_session_factory.cache_clear()
