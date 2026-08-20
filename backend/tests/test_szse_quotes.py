from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.sync.szse_quotes import decimal_or_none, quote_values, sync_quotes


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


def test_sync_quotes_continues_when_one_listing_fails(monkeypatch) -> None:
    session = MagicMock()
    listings = [
        SimpleNamespace(id=1, ticker="159001"),
        SimpleNamespace(id=2, ticker="159002"),
    ]
    session.execute.return_value.scalars.return_value = listings

    def fetch_history(_client, ticker):
        if ticker == "159001":
            raise RuntimeError("temporary source error")
        return [{"jyrq": "2026-08-18", "ss": "1.234", "cjje": "1"}]

    monkeypatch.setattr("app.sync.szse_quotes.fetch_quote_history", fetch_history)
    trade_date, count, missing = sync_quotes(
        session,
        MagicMock(),
        date(2026, 8, 18),
        datetime(2026, 8, 18, tzinfo=UTC),
    )

    assert trade_date == date(2026, 8, 18)
    assert count == 1
    assert missing == ["159001"]
