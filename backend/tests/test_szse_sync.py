from datetime import date
from decimal import Decimal

import app.sync.szse_funds as szse_funds
from app.sync.szse_funds import classify, clean_report_value, fetch_szse_funds


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


def test_fetch_funds_preserves_official_scale_date(monkeypatch) -> None:
    report = {
        "metadata": {
            "subname": "2026-08-21",
            "pagecount": 1,
            "cols": {"dqgm": "当前规模（万份）（2026-08-20）"},
        },
        "data": [row("中证500ETF嘉实", "399905 中证 500")],
    }
    monkeypatch.setattr("app.sync.szse_funds.SZSE_SEARCH_TERMS", ("中证500",))
    monkeypatch.setattr("app.sync.szse_funds.fetch_report_page", lambda *_args, **_kwargs: report)

    rows, snapshot_date = fetch_szse_funds()

    assert snapshot_date == date(2026, 8, 21)
    assert rows[0]["scale_date"] == "2026-08-20"


def test_product_summary_url_prefers_product_summary() -> None:
    page_html = """
    <a href="../disclose/instance_show_pdf_id.do?instanceid=2">招募说明书更新</a>
    <a href="../disclose/instance_show_pdf_id.do?instanceid=1">
      嘉实中证500ETF：2026基金产品资料概要更新
    </a>
    """

    assert szse_funds.product_summary_url(page_html) == (
        "http://eid.csrc.gov.cn/fund/disclose/instance_show_pdf_id.do?instanceid=1"
    )


def test_parse_fee_rates_reads_management_and_custody(monkeypatch) -> None:
    class Page:
        def extract_text(self) -> str:
            return (
                "基金运作相关费用 管 理 费 固定比例 0.15 % 基金管理人 "
                "托 管 费 年费率：0.05 % 基金托管人"
            )

    class Reader:
        def __init__(self, _content) -> None:
            self.pages = [Page()]

    monkeypatch.setattr(szse_funds, "PdfReader", Reader)

    assert szse_funds.parse_fee_rates(b"pdf") == {
        "management": Decimal("0.15"),
        "custody": Decimal("0.05"),
    }
