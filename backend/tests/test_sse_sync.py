from datetime import date
from decimal import Decimal

from app.sync.sse_funds import (
    classify,
    parse_sse_nav_records,
    sse_detail_url,
)


def row(index_name: str, display_name: str) -> dict[str, str]:
    return {
        "INDEX_NAME": index_name,
        "FUND_ABBR": display_name,
        "FUND_EXPANSION_ABBR": display_name,
    }


def test_classifies_exact_csi_500_etf() -> None:
    target = classify(row("中证小盘500指数", "中证500ETF南方"))
    assert target is not None
    assert target.family_id == "csi-500"


def test_excludes_csi_500_enhanced_and_variant_indices() -> None:
    assert classify(row("中证小盘500指数", "中证500增强ETF南方")) is None
    assert classify(row("中证500等权重指数", "500等权ETF前海开源")) is None


def test_classifies_us_index_etfs() -> None:
    assert classify(row("标准普尔500指数", "标普500ETF博时")).family_id == "sp-500"
    assert classify(row("纳斯达克100指数", "纳指ETF国泰")).family_id == "nasdaq-100"


def test_parses_sse_detail_page_nav() -> None:
    records = parse_sse_nav_records(
        {
            "code": "510500",
            "kline": [
                [20260813, 7.9705, 8.0530],
                [20260814, 8.0051, 7.9800],
            ],
        }
    )

    assert records["510500"].unit_nav == Decimal("8.0051")
    assert records["510500"].nav_date == date(2026, 8, 14)


def test_ignores_invalid_sse_detail_page_nav() -> None:
    records = parse_sse_nav_records(
        {
            "code": "510500",
            "kline": [[20260814, 0, 7.9800]],
        }
    )

    assert records == {}


def test_builds_sse_detail_url_with_category() -> None:
    assert sse_detail_url("510500", "F112") == (
        "https://etf.sse.com.cn/fundlist/funddetail/index.shtml"
        "?code=510500&category=F112"
    )
