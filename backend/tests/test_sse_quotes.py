from datetime import UTC, datetime
from decimal import Decimal

from app.sync.sse_quotes import decimal_or_none, quote_values


def test_decimal_or_none_handles_missing_values() -> None:
    assert decimal_or_none(None) is None
    assert decimal_or_none("-") is None
    assert decimal_or_none("8.053") == Decimal("8.053")


def test_quote_values_converts_official_ten_thousand_units() -> None:
    values = quote_values(
        {
            "OPEN_PRICE": "7.982",
            "HIGH_PRICE": "8.09",
            "LOW_PRICE": "7.97",
            "CLOSE_PRICE": "8.053",
            "TRADE_VOL": "18099.4",
            "TRADE_AMT": "145541.86",
        },
        datetime(2026, 8, 13, tzinfo=UTC),
    )
    assert values["close_price"] == Decimal("8.053")
    assert values["volume"] == Decimal("180994000.0")
    assert values["turnover_amount"] == Decimal("1455418600.00")
