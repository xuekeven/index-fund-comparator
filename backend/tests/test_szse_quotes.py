from datetime import UTC, datetime
from decimal import Decimal

from app.sync.szse_quotes import decimal_or_none, quote_values


def test_decimal_or_none_handles_commas_and_missing_values() -> None:
    assert decimal_or_none("-") is None
    assert decimal_or_none("17,583.93") == Decimal("17583.93")


def test_quote_values_converts_turnover_from_ten_thousand_yuan() -> None:
    values = quote_values(
        {"ss": "3.2680", "cjje": "17,583.93"},
        datetime(2026, 8, 13, tzinfo=UTC),
    )
    assert values["close_price"] == Decimal("3.2680")
    assert values["turnover_amount"] == Decimal("175839300.00")
