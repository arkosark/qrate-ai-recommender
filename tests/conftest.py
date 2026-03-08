"""
Shared fixtures for unit and E2E tests.
"""
import json
import os
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from uuid import UUID
from datetime import date

# Set test environment before any app imports
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_USER", "qrate")
os.environ.setdefault("DB_PASSWORD", "testpassword")
os.environ.setdefault("DB_NAME", "menucrawler_test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:4567")
os.environ.setdefault("DYNAMODB_SESSIONS_TABLE", "recommendation-sessions-test")
os.environ.setdefault("BEDROCK_ENDPOINT", "http://localhost:8081")
os.environ.setdefault("COGNITO_USER_POOL_ID", "test-pool")
os.environ.setdefault("COGNITO_APP_CLIENT_ID", "test-client")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_menu() -> list[dict]:
    return json.loads((FIXTURES_DIR / "sample_menu.json").read_text())


@pytest.fixture
def sample_guests() -> list[dict]:
    guests = json.loads((FIXTURES_DIR / "sample_guests.json").read_text())
    # Replace __TODAY__ birthday placeholder
    today = date.today().isoformat()
    for g in guests:
        if g.get("birthday") == "__TODAY__":
            g["birthday"] = today
    return guests


@pytest.fixture
def nut_allergy_guest(sample_guests) -> dict:
    return next(g for g in sample_guests if "Nut Allergy" in g["name"])


@pytest.fixture
def vegan_guest(sample_guests) -> dict:
    return next(g for g in sample_guests if "Vegan" in g["name"])


@pytest.fixture
def birthday_guest(sample_guests) -> dict:
    return next(g for g in sample_guests if "Birthday" in g["name"])


@pytest.fixture
def date_night_guest(sample_guests) -> dict:
    return next(g for g in sample_guests if "Date Night" in g["name"])


@pytest.fixture
def peanut_chicken() -> dict:
    menu = json.loads((FIXTURES_DIR / "sample_menu.json").read_text())
    return next(i for i in menu if "Peanut" in i["name"])


@pytest.fixture
def habanero_tacos() -> dict:
    menu = json.loads((FIXTURES_DIR / "sample_menu.json").read_text())
    return next(i for i in menu if "Habanero" in i["name"])


@pytest.fixture
def mock_db():
    """Async mock DB session for unit tests."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture
def restaurant_id() -> UUID:
    return UUID("r0000000-0000-0000-0000-000000000001")


@pytest.fixture
def session_id() -> str:
    return "test-session-001"
