from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PLATFORM_API_SRC = Path(__file__).resolve().parents[2] / "packages" / "platform-api" / "src"
if str(PLATFORM_API_SRC) not in sys.path:
    sys.path.insert(0, str(PLATFORM_API_SRC))

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.main import _cors_allow_origins


class CorsAllowOriginsTests(unittest.TestCase):
    def tearDown(self) -> None:
        for key in ("AGENT_CORE_CORS_ALLOW_ORIGINS", "AGENT_CORE_LOCAL_WEB_URL"):
            os.environ.pop(key, None)
        get_settings.cache_clear()

    def test_defaults_include_legacy_local_origins(self) -> None:
        self.assertEqual(
            _cors_allow_origins(),
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
        )

    def test_defaults_include_namespaced_local_web_origin(self) -> None:
        os.environ["AGENT_CORE_LOCAL_WEB_URL"] = "http://127.0.0.1:5328"
        get_settings.cache_clear()

        self.assertEqual(
            _cors_allow_origins(),
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5328",
            ],
        )

    def test_reads_explicit_env_driven_origin_list(self) -> None:
        os.environ["AGENT_CORE_CORS_ALLOW_ORIGINS"] = "http://localhost:5238, http://127.0.0.1:5238"
        get_settings.cache_clear()

        self.assertEqual(
            _cors_allow_origins(),
            [
                "http://localhost:5238",
                "http://127.0.0.1:5238",
            ],
        )


if __name__ == "__main__":
    unittest.main()
