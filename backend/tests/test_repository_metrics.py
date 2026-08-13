from datetime import date

from app.repository import calculate_estimated_deviation, calculate_operating_rate


def test_operating_rate_excludes_sales_service_fee() -> None:
    assert calculate_operating_rate(0.6, 0.2) == 0.8


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
