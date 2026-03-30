from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Column, MetaData, String, Table, engine_from_config, inspect, pool, text

from agent_core_platform_api.db import Base
from agent_core_platform_api import models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
ALEMBIC_VERSION_TABLE_NAME = "alembic_version"
ALEMBIC_VERSION_COLUMN_LENGTH = 128


def _ensure_alembic_version_table(connection) -> None:
    inspector = inspect(connection)
    if ALEMBIC_VERSION_TABLE_NAME not in inspector.get_table_names():
        metadata = MetaData()
        Table(
            ALEMBIC_VERSION_TABLE_NAME,
            metadata,
            Column("version_num", String(length=ALEMBIC_VERSION_COLUMN_LENGTH), nullable=False, primary_key=True),
        )
        metadata.create_all(connection)
        return

    if connection.dialect.name != "postgresql":
        return

    version_columns = {
        column["name"]: column for column in inspector.get_columns(ALEMBIC_VERSION_TABLE_NAME)
    }
    version_column = version_columns.get("version_num")
    version_length = getattr(version_column.get("type"), "length", None) if version_column else None
    if version_length is not None and version_length < ALEMBIC_VERSION_COLUMN_LENGTH:
        connection.execute(
            text(
                f"ALTER TABLE {ALEMBIC_VERSION_TABLE_NAME} "
                f"ALTER COLUMN version_num TYPE VARCHAR({ALEMBIC_VERSION_COLUMN_LENGTH})"
            )
        )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        with connection.begin():
            _ensure_alembic_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
