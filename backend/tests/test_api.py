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


def test_sync_task_history(monkeypatch) -> None:
    history = [
        {
            "time": "2026-08-31T01:00:00+00:00",
            "result": "succeeded",
            "method": "scheduled",
        }
    ]
    monkeypatch.setattr(sync_job_runner, "history", lambda task: history)

    response = client.get("/api/v1/sync-tasks/F/history")

    assert response.status_code == 200
    assert response.json() == {"items": history}
    assert client.get("/api/v1/sync-tasks/unknown/history").status_code == 422


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
    assert body["dataFreshness"] == {
        "master": None,
        "nav": None,
        "quote": None,
        "fee": None,
        "scale": None,
        "metric": None,
        "subscription": None,
    }
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


def test_investment_notes_round_trip() -> None:
    created = client.post(
        "/api/v1/notes",
        json={
            "noteDate": "2026-08-30",
            "title": "标普500观察",
            "category": "实时",
            "action": "观察",
            "sourceName": "自己总结",
            "sourceExcerpt": "等待确认方向",
            "ownSummary": "不追涨，分批处理。",
            "contentMarkdown": "- 观察波动\n- 记录失效条件",
            "tags": ["标普500", "风控"],
            "indexIds": ["sp-500"],
            "fundCodes": ["513500"],
        },
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    listed = client.get("/api/v1/notes", params={"q": "风控", "year": 2026})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [note_id]

    updated_payload = {
        **created.json(),
        "title": "标普500观察（已复盘）",
        "action": "减仓",
    }
    updated = client.put(f"/api/v1/notes/{note_id}", json=updated_payload)
    assert updated.status_code == 200
    assert updated.json()["title"] == "标普500观察（已复盘）"
    assert updated.json()["action"] == "减仓"

    deleted = client.delete(f"/api/v1/notes/{note_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.put(f"/api/v1/notes/{note_id}", json=updated_payload).status_code == 404


def test_investment_notes_validate_category_and_action() -> None:
    response = client.post(
        "/api/v1/notes",
        json={
            "noteDate": "2026-08-30",
            "title": "非法笔记",
            "category": "其他",
            "action": "梭哈",
        },
    )
    assert response.status_code == 422


def test_knowledge_articles_round_trip() -> None:
    created = client.post(
        "/api/v1/knowledge",
        json={
            "title": "美国利率体系",
            "category": "利率",
            "summary": "理解 FFR、IOER 和 ON RRP 的关系。",
            "contentMarkdown": "# 定义\n\n美联储通过利率工具影响流动性。",
            "tags": ["利率", "美国"],
            "sources": [{"name": "Federal Reserve", "url": "https://www.federalreserve.gov/"}],
            "reviewedAt": "2026-08-31",
        },
    )
    assert created.status_code == 201
    article_id = created.json()["id"]
    assert created.json()["sources"][0]["name"] == "Federal Reserve"

    listed = client.get("/api/v1/knowledge", params={"q": "FFR", "category": "利率"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [article_id]

    updated_payload = {**created.json(), "title": "美国利率体系（已复核）"}
    updated = client.put(f"/api/v1/knowledge/{article_id}", json=updated_payload)
    assert updated.status_code == 200
    assert "status" not in updated.json()
    assert updated.json()["categoryOrder"] == 0
    assert updated.json()["articleOrder"] == 0

    second = client.post(
        "/api/v1/knowledge",
        json={
            "title": "短期债券",
            "category": "资产配置",
            "contentMarkdown": "短债用于流动性管理。",
        },
    ).json()
    third = client.post(
        "/api/v1/knowledge",
        json={
            "title": "黄金",
            "category": "资产配置",
            "contentMarkdown": "黄金用于信用风险对冲。",
        },
    ).json()

    reordered = client.put(
        "/api/v1/knowledge/order",
        json={
            "categories": [
                {"category": "资产配置", "articleIds": [third["id"], second["id"]]},
                {"category": "利率", "articleIds": [article_id]},
            ]
        },
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()] == [
        third["id"], second["id"], article_id
    ]

    moved = client.put(
        "/api/v1/knowledge/order",
        json={
            "categories": [{
                "category": "资产配置",
                "articleIds": [article_id, third["id"], second["id"]],
            }]
        },
    )
    assert moved.status_code == 200
    assert moved.json()[0]["category"] == "资产配置"


    assert client.delete(f"/api/v1/knowledge/{second['id']}").status_code == 200
    assert client.delete(f"/api/v1/knowledge/{third['id']}").status_code == 200
    deleted = client.delete(f"/api/v1/knowledge/{article_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}


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
