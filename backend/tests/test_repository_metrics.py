from datetime import date

from app.repository import calculate_estimated_deviation, calculate_operating_rate


def test_operating_rate_includes_sales_service_fee() -> None:
    assert calculate_operating_rate(0.6, 0.2) == 0.8
    assert calculate_operating_rate(0.6, 0.2, 0) == 0.8
    assert calculate_operating_rate(0.6, 0.2, 0.35) == 1.15


def test_operating_rate_requires_management_and_custody_fees() -> None:
    assert calculate_operating_rate(0.6, None) is None
    assert calculate_operating_rate(None, 0.2) is None


def test_estimated_deviation_requires_matching_dates() -> None:
    assert (
        calculate_estimated_deviation(
            2.031,
            date(2026, 8, 12),
            1.9941,
            date(2026, 8, 11),
        )
        is None
    )


def test_estimated_deviation_uses_same_day_price_and_nav() -> None:
    assert calculate_estimated_deviation(
        8.053,
        date(2026, 8, 12),
        8.0472,
        date(2026, 8, 12),
    ) == 0.0721


def test_qdii_deviation_uses_newer_china_close_with_latest_us_nav() -> None:
    assert calculate_estimated_deviation(
        2.089,
        date(2026, 8, 28),
        1.946,
        date(2026, 8, 27),
        allow_lagged_nav=True,
    ) == 7.3484


def test_qdii_deviation_rejects_close_older_than_nav() -> None:
    assert calculate_estimated_deviation(
        2.089,
        date(2026, 8, 26),
        1.946,
        date(2026, 8, 27),
        allow_lagged_nav=True,
    ) is None


def test_qdii_deviation_rejects_stale_nav() -> None:
    assert calculate_estimated_deviation(
        2.089,
        date(2026, 8, 28),
        1.9318,
        date(2026, 8, 26),
        allow_lagged_nav=True,
    ) is None
