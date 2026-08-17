import argparse
import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import (
    CalculatedMetric,
    FundListing,
    FundProduct,
    FundScale,
    FundShareClass,
    IndexDefinition,
    MarketQuote,
    NavDaily,
)
from app.sync.sse_funds import (
    ASIA_SHANGHAI,
    SSE_FUND_BASE_INFO_SQL_ID,
    SSE_LIST_URL,
    SSE_SOURCE_URL,
    SSE_USER_AGENT,
    SseNavRecord,
    TARGETS,
    parse_sse_fee_rates,
    sse_detail_url,
    sync_fee_history,
    sync_nav_daily,
)


SSE_SNAPSHOT_URL = "https://yunhq.sse.com.cn:32042/v1/sh1/snap"
SSE_DAYK_URL = "https://yunhq.sse.com.cn:32042/v1/sh1/dayk"
SSE_HISTORY_BEGIN = -320
SSE_HISTORY_END = -1
SSE_HISTORY_SELECT = "date,iopv,prevClose"
SSE_SNAPSHOT_SELECT = (
    "name,last,chg_rate,change,open,prev_close,high,low,volume,amount,"
    "tradephase,cpxxextendname,iopv,fp_volume,fp_amount,fp_phase,cpxxsubtype"
)
TARGET_FAMILY_IDS = tuple(target.family_id for target in TARGETS)
RETURN_CALCULATION_VERSION = "sse-iopv-simple-return-v1"


@dataclass(frozen=True)
class SseDetailInfo:
    fee_rates: dict[str, Decimal]
    scale_yi: Decimal


@dataclass(frozen=True)
class SseSnapshot:
    code: str
    trade_date: date
    close_price: Decimal
    nav: Decimal
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    volume: Decimal | None
    turnover_amount: Decimal | None


@dataclass(frozen=True)
class ReturnMetric:
    metric_code: str
    period_start: date
    period_end: date
    start_nav: Decimal
    end_nav: Decimal
    value: Decimal


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise RuntimeError(f"Invalid SSE numeric value: {value!r}") from exc


def parse_sse_detail_info(payload: dict[str, Any]) -> SseDetailInfo:
    rows = payload.get("result")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise RuntimeError("SSE fund detail response did not contain a result")
    scale_yi = decimal_or_none(rows[0].get("SCALE"))
    if scale_yi is None or scale_yi < 0:
        raise RuntimeError("SSE fund detail response did not contain a valid SCALE")
    return SseDetailInfo(
        fee_rates=parse_sse_fee_rates(payload),
        scale_yi=scale_yi,
    )


def parse_sse_snapshot(payload: dict[str, Any]) -> SseSnapshot:
    code = str(payload.get("code") or "").strip()
    raw_date = str(payload.get("date") or "").strip()
    values = payload.get("snap")
    if not code or len(raw_date) != 8 or not isinstance(values, list) or len(values) < 13:
        raise RuntimeError("SSE fund detail snapshot was incomplete")
    try:
        trade_date = datetime.strptime(raw_date, "%Y%m%d").date()
    except ValueError as exc:
        raise RuntimeError(f"Invalid SSE snapshot date: {raw_date!r}") from exc

    close_price = decimal_or_none(values[1])
    nav = decimal_or_none(values[12])
    if close_price is None or close_price < 0 or nav is None or nav <= 0:
        raise RuntimeError(f"SSE snapshot lacked close price or NAV for {code}")
    return SseSnapshot(
        code=code,
        trade_date=trade_date,
        close_price=close_price,
        nav=nav,
        open_price=decimal_or_none(values[4]),
        high_price=decimal_or_none(values[6]),
        low_price=decimal_or_none(values[7]),
        volume=decimal_or_none(values[8]),
        turnover_amount=decimal_or_none(values[9]),
    )


def parse_sse_nav_history(payload: dict[str, Any]) -> list[SseNavRecord]:
    rows = payload.get("kline")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("SSE fund NAV history response did not contain kline rows")

    records: list[SseNavRecord] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            raise RuntimeError("SSE fund NAV history row was incomplete")
        raw_date = str(row[0])
        try:
            nav_date = datetime.strptime(raw_date, "%Y%m%d").date()
        except ValueError as exc:
            raise RuntimeError(f"Invalid SSE NAV history date: {raw_date!r}") from exc
        unit_nav = decimal_or_none(row[1])
        if unit_nav is None or unit_nav <= 0:
            raise RuntimeError(f"Invalid SSE NAV history value on {raw_date}: {row[1]!r}")
        records.append(
            SseNavRecord(
                code=str(payload.get("code") or "").strip(),
                nav_date=nav_date,
                unit_nav=unit_nav,
            )
        )
    return records


def subtract_months(value: date, months: int) -> date:
    total_months = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_return_metrics(records: list[SseNavRecord]) -> list[ReturnMetric]:
    if not records:
        return []
    by_date = {record.nav_date: record.unit_nav for record in records}
    ordered_dates = sorted(by_date)
    period_end = ordered_dates[-1]
    end_nav = by_date[period_end]
    targets = {
        "return_1m": subtract_months(period_end, 1),
        "return_3m": subtract_months(period_end, 3),
        "return_6m": subtract_months(period_end, 6),
        "return_ytd": date(period_end.year - 1, 12, 31),
        "return_1y": subtract_months(period_end, 12),
    }

    metrics: list[ReturnMetric] = []
    for metric_code, target_date in targets.items():
        eligible = [item for item in ordered_dates if item <= target_date]
        if not eligible:
            continue
        period_start = eligible[-1]
        start_nav = by_date[period_start]
        metrics.append(
            ReturnMetric(
                metric_code=metric_code,
                period_start=period_start,
                period_end=period_end,
                start_nav=start_nav,
                end_nav=end_nav,
                value=(end_nav / start_nav - Decimal("1")) * Decimal("100"),
            )
        )
    return metrics


def fetch_detail_info(
    client: httpx.Client, code: str, detail_url: str
) -> SseDetailInfo:
    response = client.get(
        SSE_LIST_URL,
        params={"sqlId": SSE_FUND_BASE_INFO_SQL_ID, "FUND_CODE": code},
        headers={"Referer": detail_url},
    )
    response.raise_for_status()
    return parse_sse_detail_info(response.json())


def fetch_snapshot(
    client: httpx.Client, code: str, detail_url: str
) -> SseSnapshot:
    response = client.get(
        f"{SSE_SNAPSHOT_URL}/{code}",
        params={"select": SSE_SNAPSHOT_SELECT},
        headers={"Referer": detail_url},
    )
    response.raise_for_status()
    return parse_sse_snapshot(response.json())


def fetch_nav_history(
    client: httpx.Client, code: str, detail_url: str
) -> tuple[list[SseNavRecord], str]:
    response = client.get(
        f"{SSE_DAYK_URL}/{code}",
        params={
            "begin": SSE_HISTORY_BEGIN,
            "end": SSE_HISTORY_END,
            "period": "day",
            "select": SSE_HISTORY_SELECT,
        },
        headers={"Referer": detail_url},
    )
    response.raise_for_status()
    records = parse_sse_nav_history(response.json())
    if any(record.code != code for record in records):
        raise RuntimeError(f"SSE NAV history code mismatch for {code}")
    return records, str(response.request.url)


def needs_nav_history_backfill(session: Session, share_id: int) -> bool:
    return not bool(
        session.scalar(
            select(NavDaily.id)
            .where(
                NavDaily.fund_share_class_id == share_id,
                NavDaily.source_url.like(f"{SSE_DAYK_URL}/%"),
            )
            .limit(1)
        )
    )


def load_nav_records(session: Session, share_id: int) -> list[SseNavRecord]:
    return [
        SseNavRecord(code="", nav_date=nav_date, unit_nav=unit_nav)
        for nav_date, unit_nav in session.execute(
            select(NavDaily.nav_date, NavDaily.unit_nav)
            .where(NavDaily.fund_share_class_id == share_id)
            .order_by(NavDaily.nav_date)
        ).all()
    ]


def sync_return_metrics(
    session: Session,
    share_id: int,
    index_definition_id: str | None,
    metrics: list[ReturnMetric],
    collected_at: datetime,
    source_url: str,
) -> None:
    for metric in metrics:
        values = {
            "index_definition_id": index_definition_id,
            "value": metric.value,
            "value_unit": "percent",
            "calculation_inputs": {
                "method": "simple_return_without_dividend_adjustment",
                "start_nav": str(metric.start_nav),
                "end_nav": str(metric.end_nav),
            },
            "source_url": source_url,
            "source_time": collected_at,
            "effective_from": collected_at,
            "collected_at": collected_at,
            "quality_status": "estimated",
        }
        statement = insert(CalculatedMetric).values(
            fund_share_class_id=share_id,
            metric_code=metric.metric_code,
            period_start=metric.period_start,
            period_end=metric.period_end,
            calculation_version=RETURN_CALCULATION_VERSION,
            **values,
        )
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_calculated_metric_identity",
                set_=values,
            )
        )


def sync_quote(
    session: Session,
    listing_id: int,
    snapshot: SseSnapshot,
    collected_at: datetime,
    source_url: str,
) -> None:
    business_time = datetime.combine(
        snapshot.trade_date, time.min, tzinfo=ASIA_SHANGHAI
    )
    values = {
        "open_price": snapshot.open_price,
        "high_price": snapshot.high_price,
        "low_price": snapshot.low_price,
        "close_price": snapshot.close_price,
        "volume": snapshot.volume,
        "turnover_amount": snapshot.turnover_amount,
        "iopv": snapshot.nav,
        "source_url": source_url,
        "source_time": business_time,
        "effective_from": business_time,
        "collected_at": collected_at,
        "quality_status": "verified",
    }
    statement = insert(MarketQuote).values(
        fund_listing_id=listing_id,
        trade_date=snapshot.trade_date,
        **values,
    )
    session.execute(
        statement.on_conflict_do_update(
            constraint="uq_market_quote_listing_date",
            set_=values,
        )
    )


def sync_scale(
    session: Session,
    product_id: int,
    trade_date: date,
    scale_yi: Decimal,
    collected_at: datetime,
    source_url: str,
) -> None:
    legacy_rows = list(session.scalars(
        select(FundScale).where(
            FundScale.fund_product_id == product_id,
            FundScale.source_url == SSE_SOURCE_URL,
        )
    ))
    for legacy in legacy_rows:
        session.delete(legacy)
    if legacy_rows:
        session.flush()

    business_time = datetime.combine(trade_date, time.min, tzinfo=ASIA_SHANGHAI)
    existing = session.scalar(
        select(FundScale)
        .where(
            FundScale.fund_product_id == product_id,
            FundScale.report_date == trade_date,
        )
        .order_by(FundScale.id.desc())
        .limit(1)
    )
    values = {
        "amount": scale_yi * Decimal("100000000"),
        "amount_cny": scale_yi * Decimal("100000000"),
        "currency": "人民币",
        "source_url": source_url,
        "source_time": business_time,
        "effective_from": business_time,
        "collected_at": collected_at,
        "quality_status": "verified",
    }
    if existing is None:
        session.add(
            FundScale(
                fund_product_id=product_id,
                report_date=trade_date,
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(existing, key, value)


def run_sync(*, dry_run: bool = False) -> tuple[int, list[date]]:
    collected_at = datetime.now(UTC)
    headers = {"User-Agent": SSE_USER_AGENT}
    with get_session_factory()() as session, httpx.Client(
        trust_env=False, timeout=30, headers=headers
    ) as client:
        rows = session.execute(
            select(
                FundListing,
                FundShareClass.id.label("share_id"),
                FundProduct.id.label("product_id"),
                FundProduct.exact_benchmark_id.label("index_definition_id"),
            )
            .join(
                FundShareClass,
                FundShareClass.id == FundListing.fund_share_class_id,
            )
            .join(FundProduct, FundProduct.id == FundShareClass.fund_product_id)
            .join(
                IndexDefinition,
                IndexDefinition.id == FundProduct.exact_benchmark_id,
            )
            .where(
                FundListing.exchange == "上交所",
                FundListing.status == "listed",
                FundShareClass.status == "active",
                FundProduct.status == "active",
                IndexDefinition.family_id.in_(TARGET_FAMILY_IDS),
            )
            .order_by(FundListing.ticker)
        ).all()
        if not rows:
            raise RuntimeError("No active target SSE listings found; run script A first")

        trade_dates: set[date] = set()
        for listing, share_id, product_id, index_definition_id in rows:
            detail_url = (
                listing.source_url
                if listing.source_url
                and "funddetail/index.shtml" in listing.source_url
                else sse_detail_url(listing.ticker)
            )
            detail = fetch_detail_info(client, listing.ticker, detail_url)
            snapshot = fetch_snapshot(client, listing.ticker, detail_url)
            if snapshot.code != listing.ticker:
                raise RuntimeError(
                    f"SSE detail code mismatch: {listing.ticker} != {snapshot.code}"
                )

            sync_fee_history(
                session,
                share_id,
                detail.fee_rates,
                collected_at,
                detail_url,
            )
            sync_nav_daily(
                session,
                share_id,
                SseNavRecord(
                    code=snapshot.code,
                    nav_date=snapshot.trade_date,
                    unit_nav=snapshot.nav,
                ),
                collected_at,
                detail_url,
            )
            metric_source_url = detail_url
            if needs_nav_history_backfill(session, share_id):
                history, metric_source_url = fetch_nav_history(
                    client, listing.ticker, detail_url
                )
                for record in history:
                    sync_nav_daily(
                        session,
                        share_id,
                        record,
                        collected_at,
                        metric_source_url,
                    )
            sync_return_metrics(
                session,
                share_id,
                index_definition_id,
                calculate_return_metrics(load_nav_records(session, share_id)),
                collected_at,
                metric_source_url,
            )
            sync_quote(
                session,
                listing.id,
                snapshot,
                collected_at,
                detail_url,
            )
            sync_scale(
                session,
                product_id,
                snapshot.trade_date,
                detail.scale_yi,
                collected_at,
                detail_url,
            )
            trade_dates.add(snapshot.trade_date)

        if dry_run:
            session.rollback()
        else:
            session.commit()
    return len(rows), sorted(trade_dates)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync target SSE ETF detail-page metrics"
    )
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    count, trade_dates = run_sync(dry_run=args.dry_run)
    action = "validated" if args.dry_run else "synced"
    dates = ", ".join(item.isoformat() for item in trade_dates)
    print(f"SSE target ETF details {action}: {count}; trade dates: {dates}")


if __name__ == "__main__":
    main()
