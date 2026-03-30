from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


def _load_bootstrap_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "bootstrap_local_namespace.py"
    spec = importlib.util.spec_from_file_location("bootstrap_local_namespace", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load bootstrap module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_contract_derives_namespaced_postgres_fields_from_product_factory() -> None:
    bootstrap = _load_bootstrap_module()

    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir) / "orcha-issue-55"
        factory_dir = worktree_path / ".agent-core"
        factory_dir.mkdir(parents=True)
        (factory_dir / "product-factory.json").write_text(
            '{"product": {"key": "orcha"}}\n',
            encoding="utf-8",
        )

        contract = bootstrap.build_contract(worktree_path=worktree_path)
        values = contract.values

        assert values["AGENT_CORE_PRODUCT_KEY"] == "orcha"
        assert int(values["AGENT_CORE_LOCAL_DATABASE_PORT"]) == 6100 + int(values["AGENT_CORE_WORKTREE_SLOT"])
        assert values["AGENT_CORE_LOCAL_DATABASE_NAME"] == "orcha"
        assert (
            values["AGENT_CORE_LOCAL_DATABASE_URL"]
            == "postgresql+psycopg://postgres:postgres@127.0.0.1:"
            f"{values['AGENT_CORE_LOCAL_DATABASE_PORT']}/orcha"
        )
        assert values["AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME"].startswith("agent-core-pg-")
        assert values["AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME"].startswith("agent-core-pg-data-")
