from datetime import date
from decimal import Decimal

from app.sync.company_official_nav import (
    harvest_product_id,
    huaan_page_count,
    parse_bosera_nav,
    parse_chinaamc_nav,
    parse_cifm_nav,
    parse_china_universal_nav,
    parse_gf_nav,
    parse_harvest_nav,
    parse_huaan_nav,
)


def test_parses_gf_official_nav() -> None:
    records = parse_gf_nav(
        {
            "data": [
                {
                    "FUNDCODE": "000055",
                    "NAVDATE": "20260827",
                    "NAVUNIT": "1.2101",
                    "NAVACCUMULATED": "1.2500",
                }
            ]
        },
        "000055",
    )

    assert records[0].nav_date == date(2026, 8, 27)
    assert records[0].unit_nav == Decimal("1.2101")
    assert records[0].accumulated_nav == Decimal("1.2500")


def test_parses_chinaamc_official_nav() -> None:
    records = parse_chinaamc_nav(
        {
            "ShowData": ["2026-08-26", "2026-08-27"],
            "danweijingzhiName": [0.2991, 0.3031],
            "leijiJingzhiName": [0.2991, 0.3031],
        },
        "015518",
    )

    assert [record.unit_nav for record in records] == [
        Decimal("0.2991"),
        Decimal("0.3031"),
    ]


def test_parses_bosera_official_nav() -> None:
    records = parse_bosera_nav(
        {
            "retCode": "0",
            "data": {
                "resultList": [
                    {
                        "fundCode": "016056",
                        "date": "20260827",
                        "netValuePer": "0.3140",
                        "totalNetValue": "0.3140",
                    }
                ]
            },
        },
        "016056",
    )

    assert records[0].unit_nav == Decimal("0.3140")


def test_parses_harvest_product_and_official_nav() -> None:
    assert harvest_product_id('<input id="product_id" value="1952" />') == "1952"
    records = parse_harvest_nav(
        {
            "results": [
                {
                    "data": [
                        {
                            "nav_date": "2026-08-27",
                            "relate_price": "0.3221",
                            "cumulative_net": "0.3221",
                        }
                    ]
                }
            ]
        },
        "016534",
    )

    assert records[0].unit_nav == Decimal("0.3221")


def test_parses_huaan_official_nav_and_pagination() -> None:
    page = """
    <tr><td class="th1">2026-08-27</td>
    <td class="th2">1.2154</td><td class="th2">1.2154</td></tr>
    <span class="curr">1</span>/264
    """
    records = parse_huaan_nav(page, "040047")

    assert records[0].unit_nav == Decimal("1.2154")
    assert huaan_page_count(page) == 264


def test_parses_cifm_official_nav_xml() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Funds><Fund FundCode="017643" FundDate="2026-08-27"
    NetValue="0.2523" TotalNetValue="0.2523" /></Funds>"""
    records = parse_cifm_nav(content, "017643")

    assert records[0].nav_date == date(2026, 8, 27)
    assert records[0].unit_nav == Decimal("0.2523")



def test_parses_china_universal_official_nav() -> None:
    records = parse_china_universal_nav(
        {
            "returnCode": 0,
            "body": [
                {
                    "fundId": "018968",
                    "navDate": "2026-08-27",
                    "navDisplay": "1.7504",
                    "sumOfNav": "1.7504",
                }
            ],
        },
        "018968",
    )

    assert records[0].nav_date == date(2026, 8, 27)
    assert records[0].unit_nav == Decimal("1.7504")
