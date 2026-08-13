from app.sync.sse_funds import classify


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
