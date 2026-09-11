from datetime import date
from decimal import Decimal
import json

import pytest

from app.sync.sse_details import (
    calculate_return_metrics,
    eid_nav_query_data,
    is_legacy_iopv_nav_source,
    merge_product_summary_fee_rates,
    parse_eid_nav_report,
    parse_sse_detail_info,
    parse_sse_nav_history,
    parse_sse_snapshot,
)


def test_parses_sse_detail_scale_without_using_exchange_fee_rates() -> None:
    detail = parse_sse_detail_info(
        {
            "result": [
                {
                    "FUND_CODE": "510500",
                    "MANAGEMENT_RATE": "0.15",
                    "TRUSTEESHIP_RATE": "0.05",
                    "SCALE": "407.2716",
                }
            ]
        }
    )

    assert detail.fee_rates == {}
    assert detail.scale_yi == Decimal("407.2716")


def test_uses_product_summary_pdf_for_all_fee_rates() -> None:
    detail = parse_sse_detail_info(
        {
            "result": [
                {
                    "MANAGEMENT_RATE": "0.15",
                    "TRUSTEESHIP_RATE": "0.05",
                    "SCALE": "1",
                }
            ]
        }
    )

    merged = merge_product_summary_fee_rates(
        detail,
        {
            "management": Decimal("0.60"),
            "custody": Decimal("0.20"),
            "comprehensive_operating": Decimal("0.80"),
        },
        "https://example.com/summary.pdf",
    )

    assert merged.fee_rates == {
        "management": Decimal("0.60"),
        "custody": Decimal("0.20"),
        "comprehensive_operating": Decimal("0.80"),
    }
    assert merged.fee_source_url == "https://example.com/summary.pdf"


def test_parses_sse_detail_snapshot() -> None:
    snapshot = parse_sse_snapshot(
        {
            "code": "510500",
            "date": 20260814,
            "snap": [
                "500ETF",
                7.998,
                0.23,
                0.018,
                8.0,
                7.98,
                8.024,
                7.91,
                254678534,
                2032474227,
                "E110",
                "中证500ETF南方",
                8.0051,
            ],
        }
    )

    assert snapshot.code == "510500"
    assert snapshot.trade_date == date(2026, 8, 14)
    assert snapshot.close_price == Decimal("7.998")
    assert snapshot.iopv == Decimal("8.0051")
    assert snapshot.volume == Decimal("254678534")
    assert snapshot.turnover_amount == Decimal("2032474227")


def test_rejects_incomplete_sse_snapshot() -> None:
    with pytest.raises(RuntimeError, match="incomplete"):
        parse_sse_snapshot({"code": "510500", "date": 20260814, "snap": []})


def test_eid_nav_query_and_parser_use_formal_date_and_exact_code() -> None:
    query = json.loads(
        eid_nav_query_data("513500", date(2025, 8, 1), date(2026, 9, 4))
    )
    assert {item["name"]: item["value"] for item in query}["fundCode"] == "513500"

    records = parse_eid_nav_report(
        {
            "aaData": [
                {
                    "code": "513500",
                    "valuationDate": "2026-09-03",
                    "shareNetValue": "2.4849",
                },
                {
                    "code": "513650",
                    "valuationDate": "2026-09-03",
                    "shareNetValue": "1.8926",
                },
            ]
        },
        "513500",
    )

    assert [(record.nav_date, record.unit_nav) for record in records] == [
        (date(2026, 9, 3), Decimal("2.4849"))
    ]


def test_identifies_only_legacy_sse_iopv_nav_sources() -> None:
    assert is_legacy_iopv_nav_source(
        "https://yunhq.sse.com.cn:32042/v1/sh1/dayk/513500?begin=-320"
    )
    assert is_legacy_iopv_nav_source(
        "https://etf.sse.com.cn/fundlist/funddetail/index.shtml?code=513500"
    )
    assert not is_legacy_iopv_nav_source(
        "http://eid.csrc.gov.cn/fund/disclose/getPublicFundJZInfoMore.do"
    )


def test_parses_sse_nav_history() -> None:
    records = parse_sse_nav_history(
        {
            "code": "510500",
            "kline": [
                [20260813, 7.9802, 7.950],
                [20260814, 8.0051, 7.980],
            ],
        }
    )

    assert [(item.nav_date, item.unit_nav) for item in records] == [
        (date(2026, 8, 13), Decimal("7.9802")),
        (date(2026, 8, 14), Decimal("8.0051")),
    ]


def test_calculates_five_simple_return_periods_from_nearest_prior_nav() -> None:
    records = parse_sse_nav_history(
        {
            "code": "510500",
            "kline": [
                [20250814, 100, 0],
                [20251231, 110, 0],
                [20260213, 120, 0],
                [20260514, 130, 0],
                [20260714, 140, 0],
                [20260814, 150, 0],
            ],
        }
    )

    metrics = {item.metric_code: item for item in calculate_return_metrics(records)}

    assert set(metrics) == {
        "return_1m",
        "return_3m",
        "return_6m",
        "return_ytd",
        "return_1y",
    }
    assert metrics["return_1m"].period_start == date(2026, 7, 14)
    assert metrics["return_3m"].period_start == date(2026, 5, 14)
    assert metrics["return_6m"].period_start == date(2026, 2, 13)
    assert metrics["return_ytd"].period_start == date(2025, 12, 31)
    assert metrics["return_1y"].period_start == date(2025, 8, 14)
    assert metrics["return_1m"].value == Decimal("7.142857142857142857142857100")
    assert metrics["return_6m"].value == Decimal("25.00")
    assert metrics["return_1y"].value == Decimal("50.0")



def test_does_not_calculate_return_from_stale_isolated_nav() -> None:
    records = parse_sse_nav_history(
        {
            "code": "018969",
            "kline": [
                [20230802, 1.0000, 0],
                [20260824, 1.7227, 0],
                [20260827, 1.7616, 0],
            ],
        }
    )

    assert calculate_return_metrics(records) == []
