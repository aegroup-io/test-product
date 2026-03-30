from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import alembic.command
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import run_database_migrations
from agent_core_platform_api.models import OrchestrationLane


def _alembic_config(database_url: str) -> Config:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str((api_root / "migrations").resolve()))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_run_database_migrations_accepts_percent_encoded_database_urls(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        api_root = Path(__file__).resolve().parents[1]
        alembic_ini = Path(temp_dir) / "alembic.ini"
        alembic_ini.write_text((api_root / "alembic.ini").read_text(encoding="utf-8"), encoding="utf-8")
        database_url = "postgresql+psycopg://orchaadmin:p%2Bass%21word@db.example.com:5432/orcha"
        captured: dict[str, str] = {}

        def fake_upgrade(config: Config, revision: str) -> None:
            captured["revision"] = revision
            captured["database_url"] = config.get_main_option("sqlalchemy.url")
            captured["script_location"] = config.get_main_option("script_location")

        get_settings.cache_clear()
        monkeypatch.setenv("AGENT_CORE_ALEMBIC_CONFIG", str(alembic_ini))
        monkeypatch.setenv("AGENT_CORE_DATABASE_URL", database_url)
        monkeypatch.setattr(alembic.command, "upgrade", fake_upgrade)

        try:
            run_database_migrations()
        finally:
            get_settings.cache_clear()

        assert captured["revision"] == "head"
        assert captured["database_url"] == database_url
        assert captured["script_location"] == str((alembic_ini.parent / "migrations").resolve())


def test_scheduler_claim_guard_migration_cancels_duplicate_active_lanes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}"
        config = _alembic_config(database_url)
        command.upgrade(config, "0008_product_seed_jobs")

        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        work_item_id = uuid.uuid4()
        metadata = MetaData()
        organizations = Table("organizations", metadata, autoload_with=engine)
        products = Table("products", metadata, autoload_with=engine)
        repositories = Table("repository_bindings", metadata, autoload_with=engine)
        work_items = Table("work_items", metadata, autoload_with=engine)
        lanes = Table("orchestration_lanes", metadata, autoload_with=engine)
        product_id = uuid.uuid4().hex
        repo_id = uuid.uuid4().hex
        with engine.begin() as connection:
            org_id = connection.execute(
                select(organizations.c.org_id).where(organizations.c.slug == "primary")
            ).scalar_one()
            connection.execute(
                products.insert().values(
                    product_id=product_id,
                    org_id=org_id,
                    key="apollo",
                    name="Apollo",
                    status="Active",
                    setup_state="ready",
                    setup_diagnostics=[],
                    effective_config={"execution": {"profile": "standard-python", "max_concurrent_lanes": 1}},
                    operator_overrides={},
                )
            )
            connection.execute(
                repositories.insert().values(
                    repo_id=repo_id,
                    product_id=product_id,
                    github_repository_node_id="R_repo",
                    owner="aegroup-io",
                    name="apollo",
                    default_branch="dev",
                    visibility="private",
                    raw_payload={},
                )
            )
            connection.execute(
                work_items.insert().values(
                    work_item_id=work_item_id.hex,
                    repo_id=repo_id,
                    github_issue_node_id="I_issue",
                    issue_number=13,
                    title="Duplicate active lanes",
                    status="Ready",
                    labels=[],
                    assignees=[],
                    dependencies=[],
                    dependency_state="clear",
                    dependency_details=[],
                    linked_prs=[],
                    eligibility_flags=["eligible"],
                    handoff_status="none",
                    repair_reasons=[],
                    raw_payload={},
                )
            )
            connection.execute(
                lanes.insert(),
                [
                    {
                        "lane_id": uuid.uuid4().hex,
                        "product_id": product_id,
                        "repo_id": repo_id,
                        "work_item_id": work_item_id.hex,
                        "attempt": 1,
                        "state": "Claimed",
                        "claimed_at": datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
                    },
                    {
                        "lane_id": uuid.uuid4().hex,
                        "product_id": product_id,
                        "repo_id": repo_id,
                        "work_item_id": work_item_id.hex,
                        "attempt": 2,
                        "state": "Running",
                        "claimed_at": None,
                    },
                ],
            )

        command.upgrade(config, "head")

        with Session(engine) as session:
            lanes = (
                session.query(OrchestrationLane)
                .filter(OrchestrationLane.work_item_id == work_item_id)
                .order_by(OrchestrationLane.attempt.asc())
                .all()
            )
            assert [lane.state for lane in lanes] == ["Claimed", "Cancelled"]
            assert lanes[1].finished_at is not None
            assert lanes[1].last_error is not None
            assert "duplicate active lane ownership" in lanes[1].last_error
