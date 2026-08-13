from app.sync.szse_funds import classify, clean_report_value


def row(name: str, index_code: str) -> dict[str, str]:
    return {
        "sys_key": "159922",
        "kzjcurl": name,
        "nhzs": index_code,
        "dqgm": "1,000.00",
        "glrmc": "测试基金",
    }


def test_clean_report_value_removes_links_and_decodes_entities() -> None:
    assert clean_report_value("<a><u>159922</u></a>&nbsp;") == "159922"


def test_classifies_exact_csi_500_and_excludes_enhanced() -> None:
    assert classify(row("中证500ETF嘉实", "399905 中证 500")).family_id == "csi-500"
    assert classify(row("中证500增强ETF景顺", "000905")) is None


def test_classifies_sp500_net_return_separately() -> None:
    target = classify(row("标普500ETF华夏", "SPXNTR"))
    assert target is not None
    assert target.definition_id == "sp-500-net-return-cny"


def test_classifies_ndx_and_excludes_nasdaq_technology() -> None:
    assert classify(row("纳指ETF广发", "NDX")).family_id == "nasdaq-100"
    assert classify(row("纳指科技ETF景顺", "NDXTMC")) is None
