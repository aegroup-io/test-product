import os
from pathlib import Path

from .product_defaults import (
    APP_NAME,
    CRYPTO_SEED,
    DATABASE_URL,
    INITIAL_ORG_NAME,
    INITIAL_ORG_SLUG,
)

API_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("AGENT_CORE_APP_NAME", APP_NAME)
os.environ.setdefault("AGENT_CORE_DATABASE_URL", DATABASE_URL)
os.environ.setdefault("AGENT_CORE_CRYPTO_SEED", CRYPTO_SEED)
os.environ.setdefault("AGENT_CORE_INITIAL_ORG_NAME", INITIAL_ORG_NAME)
os.environ.setdefault("AGENT_CORE_INITIAL_ORG_SLUG", INITIAL_ORG_SLUG)
os.environ.setdefault("AGENT_CORE_ALEMBIC_CONFIG", str(API_ROOT / "alembic.ini"))

from agent_core_platform_api.main import app
