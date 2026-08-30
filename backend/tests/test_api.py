from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.sync_jobs import SyncJobBusyError, sync_job_runner


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


def test_readiness() -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_documentation_is_disabled() -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_frontend_rejects_path_traversal() -> None:
    response = client.get("/%2E%2E/backend/app/main.py")
    assert response.status_code in {200, 404, 503}
    assert "from fastapi import" not in response.text


def test_frontend_serves_spa_fallback() -> None:
    response = client.get("/some/client/route")
    assert response.status_code == 200
    assert "<div id=\"root\"></div>" in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_frontend_serves_built_asset() -> None:
    index = client.get("/")
    asset_path = index.text.split('src="', 1)[1].split('"', 1)[0]
    response = client.get(asset_path.removeprefix("/indexfund"))
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_unknown_api_route_remains_404() -> None:
    assert client.get("/api/v1/not-a-route").status_code == 404


def test_sync_task_status_and_start(monkeypatch) -> None:
    snapshot = {
        "activeJob": None,
        "currentScript": None,
        "tasks": {"all": {"status": "idle"}},
    }
    monkeypatch.setattr(sync_job_runner, "snapshot", lambda: snapshot)
    monkeypatch.setattr(
        sync_job_runner,
        "start",
        lambda task: {**snapshot, "activeJob": task},
    )

    assert client.get("/api/v1/sync-tasks").json() == snapshot
    response = client.post("/api/v1/sync-tasks/D")
    assert response.status_code == 202
    assert response.json()["activeJob"] == "D"


def test_sync_task_rejects_unknown_or_overlapping_job(monkeypatch) -> None:
    assert client.post("/api/v1/sync-tasks/unknown").status_code == 422

    def raise_busy(_task):
        raise SyncJobBusyError("正在执行")

    monkeypatch.setattr(sync_job_runner, "start", raise_busy)
    response = client.post("/api/v1/sync-tasks/A")
    assert response.status_code == 409
    assert response.json()["detail"] == "正在执行"


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
    assert body["lastSyncedAt"] is None
    assert all(item["tradingVenue"] == "场外" for item in body["items"])
    assert all(item["tags"] == [] for item in body["items"])


def test_single_user_fund_tags_round_trip() -> None:
    response = client.put(
        "/api/v1/funds/006075/tags",
        json={"tags": ["favorite", "holding", "recurring"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "fundCode": "006075",
        "tags": ["favorite", "holding", "recurring"],
    }

    funds = client.get("/api/v1/indices/sp-500/funds", params={"venue": "场外"})
    tagged_fund = next(
        item for item in funds.json()["items"] if item["code"] == "006075"
    )
    assert tagged_fund["tags"] == ["favorite", "holding", "recurring"]

    cleared = client.put("/api/v1/funds/006075/tags", json={"tags": []})
    assert cleared.status_code == 200
    assert cleared.json()["tags"] == []


def test_single_user_fund_tags_validate_tag_and_fund() -> None:
    invalid_tag = client.put(
        "/api/v1/funds/006075/tags",
        json={"tags": ["unknown"]},
    )
    missing_fund = client.put(
        "/api/v1/funds/not-found/tags",
        json={"tags": ["favorite"]},
    )

    assert invalid_tag.status_code == 422
    assert missing_fund.status_code == 404


def test_filter_exchange_with_repeated_query_parameters() -> None:
    response = client.get(
        "/api/v1/indices/csi-500/funds",
        params=[
            ("venue", "场内"),
            ("exchange", "深交所"),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["code"] for item in body["items"]] == ["159922"]


def test_compare_returns_warning_for_cross_index_selection() -> None:
    response = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", "510500"), ("fundCodes", "006075")],
    )
    assert response.status_code == 200
    assert response.json()["warnings"] == [
        "所选基金不属于同一指数，不建议直接比较跟踪表现。"
    ]


def test_compare_warns_for_different_exact_benchmarks() -> None:
    response = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", "513500"), ("fundCodes", "050025")],
    )
    assert response.status_code == 200
    assert response.json()["warnings"] == [
        "所选基金的精确跟踪基准不同，请结合各基金合同口径比较。"
    ]


def test_compare_requires_between_two_and_four_funds() -> None:
    too_few = client.get("/api/v1/comparisons", params={"fundCodes": "510500"})
    too_many = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", code) for code in ("1", "2", "3", "4", "5")],
    )
    assert too_few.status_code == 422
    assert too_many.status_code == 422


def test_compare_requires_distinct_fund_codes() -> None:
    response = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", "510500"), ("fundCodes", "510500")],
    )
    assert response.status_code == 422


def test_compare_requires_two_matching_funds() -> None:
    response = client.get(
        "/api/v1/comparisons",
        params=[("fundCodes", "510500"), ("fundCodes", "not-found")],
    )
    assert response.status_code == 404


def test_nav_supports_date_range_and_limit() -> None:
    response = client.get(
        "/api/v1/funds/510500/nav",
        params={"startDate": "2026-08-01", "endDate": "2026-08-31", "limit": 3},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert items == sorted(items, key=lambda item: item["date"])


def test_nav_rejects_reversed_date_range() -> None:
    response = client.get(
        "/api/v1/funds/510500/nav",
        params={"startDate": "2026-08-31", "endDate": "2026-08-01"},
    )
    assert response.status_code == 422


def test_sample_operating_rate_and_deviation_follow_display_contract() -> None:
    response = client.get("/api/v1/indices/sp-500/funds")
    assert response.status_code == 200
    funds = {item["code"]: item for item in response.json()["items"]}
    assert funds["006075"]["expenseRate"] == 0.8
    assert funds["006075"]["salesServiceFee"] == 0.35
    assert funds["513500"]["estimatedDeviation"] is None


def test_unknown_index_is_404() -> None:
    response = client.get("/api/v1/indices/not-an-index/funds")
    assert response.status_code == 404
