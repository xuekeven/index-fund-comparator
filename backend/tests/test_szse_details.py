from datetime import date
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
