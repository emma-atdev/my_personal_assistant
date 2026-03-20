"""backend/app.py FastAPI 엔드포인트 테스트."""

import pytest
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_notes_empty() -> None:
    response = client.get("/api/notes")
    assert response.status_code == 200
    assert "notes" in response.json()
    assert isinstance(response.json()["notes"], list)


def test_search_notes_empty() -> None:
    response = client.get("/api/notes/search", params={"q": "없는키워드xyz"})
    assert response.status_code == 200
    assert "result" in response.json()


def test_get_costs_empty() -> None:
    response = client.get("/api/costs")
    assert response.status_code == 200
    assert "summary" in response.json()


def test_get_latest_briefing_empty() -> None:
    response = client.get("/api/briefing/latest")
    assert response.status_code == 200
    assert "briefing" in response.json()
