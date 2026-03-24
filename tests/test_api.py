"""backend/app.py FastAPI 엔드포인트 테스트."""

from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_costs_empty() -> None:
    response = client.get("/api/costs")
    assert response.status_code == 200
    assert "summary" in response.json()
