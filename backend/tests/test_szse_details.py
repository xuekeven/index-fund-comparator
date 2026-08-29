from datetime import date
import json
from decimal import Decimal

import app.sync.szse_details as szse_details


def test_parse_nav_report_reads_official_nav_rows() -> None:
    records = szse_details.parse_nav_report(
        [
            {
                "data": [
                    {
                        "fund_code": "159922",
                        "nav_date": "2026-08-20",
                        "nav_per_share": "3.1922",
                    },
                    {
                        "fund_code": "159999",
                        "nav_date": "2026-08-20",
                        "nav_per_share": "1.0000",
                    },
                ],
                "error": None,
            }
        ],
        "159922",
    )

    assert [(record.nav_date, record.unit_nav) for record in records] == [
        (date(2026, 8, 20), Decimal("3.1922"))
    ]


def test_eid_nav_query_and_parser_use_exact_etf_code() -> None:
    query = json.loads(
        szse_details.eid_nav_query_data(
            "159513", date(2025, 8, 21), date(2026, 8, 21)
        )
    )
    assert {item["name"]: item["value"] for item in query}["fundCode"] == "159513"

    records = szse_details.parse_eid_nav_report(
        {
            "aaData": [
                {
                    "code": "159513",
                    "valuationDate": "2026-08-20",
                    "shareNetValue": "1.6496",
                },
                {
                    "code": "159999",
                    "valuationDate": "2026-08-20",
                    "shareNetValue": "1.0000",
                },
            ]
        },
        "159513",
    )
    assert [(record.nav_date, record.unit_nav) for record in records] == [
        (date(2026, 8, 20), Decimal("1.6496"))
    ]


def test_merge_nav_uses_newest_date_from_either_official_source() -> None:
    eid = [
        szse_details.SseNavRecord("159513", date(2026, 8, 19), Decimal("1.66")),
        szse_details.SseNavRecord("159513", date(2026, 8, 20), Decimal("1.67")),
    ]
    szse = [
        szse_details.SseNavRecord("159513", date(2026, 8, 19), Decimal("1.6625"))
    ]
    records = szse_details.merge_nav_records(eid, szse)

    assert records[0].unit_nav == Decimal("1.6625")
    assert records[-1].nav_date == date(2026, 8, 20)
    assert records[-1].unit_nav == Decimal("1.67")
    assert szse_details.latest_nav_on_or_before(
        records, date(2026, 8, 21)
    ) == Decimal("1.67")

    newer_szse = szse_details.merge_nav_records(
        eid,
        [
            szse_details.SseNavRecord(
                "159513", date(2026, 8, 21), Decimal("1.68")
            )
        ],
    )
    assert newer_szse[-1].nav_date == date(2026, 8, 21)
    assert newer_szse[-1].unit_nav == Decimal("1.68")


def test_estimated_scale_uses_official_share_count_and_same_day_nav() -> None:
    assert szse_details.estimated_scale_cny(
        Decimal("273867.67"), Decimal("3.1922")
    ) == Decimal("8742403761.740000")


def test_select_quote_row_supports_latest_and_explicit_dates() -> None:
    history = [
        {"jyrq": "2026-08-20", "ss": "3.1", "cjje": "1"},
        {"jyrq": "2026-08-19", "ss": "3.0", "cjje": "2"},
    ]

    latest_date, latest = szse_details.select_quote_row(history, None)
    requested_date, requested = szse_details.select_quote_row(
        history, date(2026, 8, 19)
    )

    assert latest_date == date(2026, 8, 20)
    assert latest["ss"] == "3.1"
    assert requested_date == date(2026, 8, 19)
    assert requested["ss"] == "3.0"

    assert [item[0] for item in szse_details.select_quote_rows(history, None)] == [
        date(2026, 8, 20),
        date(2026, 8, 19),
    ]
