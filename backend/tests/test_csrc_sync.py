from datetime import date
from io import BytesIO

from openpyxl import Workbook

from app.sync.csrc_funds import (
    classify_product,
    discovery_name,
    extract_index_download_url,
    is_exchange_or_lof_code,
    parse_fund_detail,
    parse_nav_rows,
    parse_product_index,
    share_identity,
    snapshot_date_from_url,
)


def test_classifies_target_off_exchange_funds_and_excludes_variants() -> None:
    assert classify_product("嘉实中证500ETF联接")[0].family_id == "csi-500"
    assert classify_product("南方纳斯达克100指数发起（QDII）")[0].family_id == "nasdaq-100"
    assert classify_product("天弘标普500发起（QDII-FOF）")[0].family_id == "sp-500"
    assert classify_product("大成标普500等权重指数(QDII)") is None
    assert classify_product("华夏中证500指数增强") is None
    assert classify_product("博时纳斯达克100ETF") is None
    assert classify_product("鹏华中证500指数（LOF）") is None
    assert is_exchange_or_lof_code("513110")
    assert is_exchange_or_lof_code("160213")
    assert not is_exchange_or_lof_code("050025")


def test_parses_csrc_product_index() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["公募基金产品索引（截至20260630）"])
    sheet.append(["序号", "基金代码", "基金简称", "设立日期"])
    sheet.append([1, 8, "嘉实中证500ETF联接", "2013-03-22"])
    sheet.append([2, "510500", "中证500ETF", "2013-02-06"])
    sheet.append([3, "513110", "纳指100", "2022-04-13"])
    output = BytesIO()
    workbook.save(output)

    candidates, snapshot_date = parse_product_index(output.getvalue())

    assert snapshot_date == date(2026, 6, 30)
    assert [(item.code, item.product_structure) for item in candidates] == [
        ("000008", "ETF联接基金")
    ]


def test_extracts_relative_index_download_url() -> None:
    page = '<a href="1029655/files/public-funds.xlsx">download</a>'
    assert extract_index_download_url(page) == (
        "https://www.csrc.gov.cn/csrc/c101900/c1029655/"
        "1029655/files/public-funds.xlsx"
    )
    assert snapshot_date_from_url(
        "https://example.test/公募基金产品索引（截至20260630）.xlsx"
    ) == date(2026, 6, 30)


def test_parses_eid_detail_page() -> None:
    page = """
    <td class="title_tu">博时标普500ETF联接(050025)</td>
    <td>基金名称</td><td>博时标普500交易型开放式指数证券投资基金联接基金</td>
    <td>基金代码</td><td>050025</td>
    <td>基金管理人</td><td>博时基金管理有限公司</td>
    <td>基金合同生效日期</td><td>2012-06-14</td>
    """
    detail = parse_fund_detail(3201, page)
    assert detail.short_name == "博时标普500ETF联接"
    assert detail.manager == "博时基金管理有限公司"
    assert detail.inception_date == date(2012, 6, 14)


def test_discovers_share_identity_and_filters_product_level_nav_rows() -> None:
    rows = [
        {
            "code": "050025",
            "shortName": "博时标普500ETF联接A",
            "valuationDate": "2026-08-12",
            "shareNetValue": "5.6433",
            "totalNetValue": "5.7023",
            "fund": {"idStr": 3201},
        },
        {
            "code": "006075",
            "shortName": "博时标普500ETF联接C",
            "valuationDate": "2026-08-12",
            "shareNetValue": "5.1234",
            "totalNetValue": "5.1234",
            "fund": {"idStr": 3201},
        },
        {
            "code": "050025",
            "shortName": "博时标普500ETF联接",
            "valuationDate": "2026-08-12",
            "shareNetValue": "",
            "fund": {"idStr": 3201},
        },
    ]
    records = parse_nav_rows(rows, 3201)
    assert [(item.code, item.share_class) for item in records] == [
        ("006075", "C"),
        ("050025", "A"),
    ]
    assert discovery_name("建信纳斯达克100指数(QDII)A人民币") == (
        "建信纳斯达克100指数(QDII)"
    )
    assert share_identity("某基金美元现汇A") == ("A", "美元", "现汇")
