from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


client = TestClient(app)


def test_database_url_accepts_standard_environment_name(monkeypatch) -> None:
    database_url = "postgresql+psycopg://user:secret@localhost:5432/index_fund_comparator"
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert Settings().database_url == database_url


def test_standard_postgresql_url_uses_psycopg_driver(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:secret@localhost:5432/index_fund_comparator"
    )
    assert (
        Settings().sqlalchemy_database_url
        == "postgresql+psycopg://user:secret@localhost:5432/index_fund_comparator"
    )


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dataMode"] == "sample"


def test_api_documentation_is_disabled() -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_indices_include_fund_counts() -> None:
    response = client.get("/api/v1/indices")
    assert response.status_code == 200
    indices = response.json()
    assert [item["id"] for item in indices] == ["csi-500", "sp-500", "nasdaq-100"]
    assert sum(item["fundCount"] for item in indices) == 6


def test_filter_funds_by_venue() -> None:
    response = client.get("/api/v1/indices/sp-500/funds", params={"venue": "场外"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["tradingVenue"] == "场外" for item in body["items"])


def test_compare_returns_warning_for_cross_index_selection() -> None:
    response = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", "510500"), ("fundCodes", "006075")],
    )
    assert response.status_code == 200
    assert len(response.json()["warnings"]) == 1


def test_unknown_index_is_404() -> None:
    response = client.get("/api/v1/indices/not-an-index/funds")
    assert response.status_code == 404
