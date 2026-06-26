"""Shared test fixtures.

Puts the backend package on the import path and exposes a FastAPI TestClient
plus the public sample-case pack.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE_FILE = REPO_ROOT / "SUST_Preli_Sample_Cases.json"


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def sample_cases() -> list[dict]:
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.fixture(scope="session")
def allowed_enums() -> dict:
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    return data["_meta"]["allowed_enums"]
