import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
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
from app.sync.csrc_funds import EID_NAV_URL
from app.sync.sse_details import calculate_return_metrics
from app.sync.sse_funds import ASIA_SHANGHAI, SseNavRecord
from app.sync.szse_funds import (
    SZSE_REPORT_URL,
    SZSE_SOURCE_URL,
    clean_report_value,
    fetch_szse_funds,
)
from app.sync.szse_quotes import fetch_quote_history, quote_values


SZSE_NAV_CATALOG_ID = "1785_child"
SZSE_NAV_SOURCE_URL = "https://www.szse.cn/market/fund/list/stockFundList/index.html"
RETURN_CALCULATION_VERSION = "szse-official-nav-simple-return-v1"
NAV_BACKFILL_DAYS = 400
NAV_PAGE_SIZE = 500
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SzseDetailStats:
    funds: int
    quotes: int
    nav_rows: int
    scales: int
    failures: tuple[str, ...] = ()


def decimal_or_none(value: Any) -> Decimal | None:
    cleaned = str(value or "").replace(",", "").strip()
    if cleaned in ("", "-"):
        return None
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise RuntimeError(f"Invalid SZSE numeric value: {value!r}") from exc
    return result


def parse_nav_report(payload: Any, ticker: str) -> list[SseNavRecord]:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError(f"SZSE NAV report returned an unexpected payload for {ticker}")
    report = payload[0]
    if report.get("error"):
        raise RuntimeError(f"SZSE NAV report error for {ticker}: {report['error']}")

    records: list[SseNavRecord] = []
    for row in report.get("data") or []:
        code = clean_report_value(row.get("fund_code"))
        if code != ticker:
            continue
        try:
            nav_date = date.fromisoformat(clean_report_value(row.get("nav_date")))
        except ValueError as exc:
            raise RuntimeError(f"Invalid SZSE NAV date for {ticker}") from exc
        unit_nav = decimal_or_none(clean_report_value(row.get("nav_per_share")))
        if unit_nav is None or unit_nav <= 0:
            raise RuntimeError(f"Invalid SZSE NAV value for {ticker} on {nav_date}")
        records.append(SseNavRecord(code=ticker, nav_date=nav_date, unit_nav=unit_nav))
    if not records:
        raise RuntimeError(f"SZSE NAV report did not contain valid rows for {ticker}")
    return sorted(records, key=lambda item: item.nav_date)


def fetch_nav_records(client: httpx.Client, ticker: str) -> tuple[list[SseNavRecord], str]:
    response = client.get(
        SZSE_REPORT_URL,
        params={
            "SHOWTYPE": "JSON",
            "CATALOGID": SZSE_NAV_CATALOG_ID,
            "TABKEY": "tab1",
            "txtDm": ticker,
        },
        headers={"Referer": SZSE_NAV_SOURCE_URL},
    )
    response.raise_for_status()
    return parse_nav_report(response.json(), ticker), str(response.request.url)


def eid_nav_query_data(ticker: str, start_date: date, end_date: date) -> str:
    data = [
        {"name": "sEcho", "value": 1},
        {"name": "iColumns", "value": 5},
        {"name": "sColumns", "value": ""},
        {"name": "iDisplayStart", "value": 0},
        {"name": "iDisplayLength", "value": NAV_PAGE_SIZE},
        {"name": "fundType", "value": "all"},
        {"name": "fundCompanyShortName", "value": ""},
        {"name": "fundCode", "value": ticker},
        {"name": "fundName", "value": ""},
        {"name": "startDate", "value": start_date.isoformat()},
        {"name": "endDate", "value": end_date.isoformat()},
    ]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def parse_eid_nav_report(payload: Any, ticker: str) -> list[SseNavRecord]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"EID NAV report returned an unexpected payload for {ticker}")
    records: dict[date, SseNavRecord] = {}
    for row in payload.get("aaData") or []:
        if str(row.get("code") or "").strip() != ticker:
            continue
        try:
            nav_date = date.fromisoformat(str(row.get("valuationDate") or "").strip())
        except ValueError as exc:
            raise RuntimeError(f"Invalid EID NAV date for {ticker}") from exc
        unit_nav = decimal_or_none(row.get("shareNetValue"))
        if unit_nav is None or unit_nav <= 0:
            raise RuntimeError(f"Invalid EID NAV value for {ticker} on {nav_date}")
        records[nav_date] = SseNavRecord(ticker, nav_date, unit_nav)
    if not records:
        raise RuntimeError(f"EID NAV report did not contain valid rows for {ticker}")
    return [records[item] for item in sorted(records)]


def fetch_eid_nav_records(
    client: httpx.Client, ticker: str, end_date: date
) -> tuple[list[SseNavRecord], str]:
    response = client.get(
        EID_NAV_URL,
        params={
            "aoData": eid_nav_query_data(
                ticker, end_date - timedelta(days=NAV_BACKFILL_DAYS), end_date
            )
        },
    )
    response.raise_for_status()
    return parse_eid_nav_report(response.json(), ticker), str(response.request.url)


def merge_nav_records(*groups: list[SseNavRecord]) -> list[SseNavRecord]:
    records = {
        record.nav_date: record
        for group in groups
        for record in group
    }
    return [records[item] for item in sorted(records)]


def latest_nav_on_or_before(
    records: list[SseNavRecord], target_date: date
) -> Decimal | None:
    eligible = [record for record in records if record.nav_date <= target_date]
    return eligible[-1].unit_nav if eligible else None


def estimated_scale_cny(scale_wan_shares: Decimal, unit_nav: Decimal) -> Decimal:
    if scale_wan_shares < 0 or unit_nav <= 0:
        raise RuntimeError("SZSE scale estimate requires nonnegative shares and positive NAV")
    return scale_wan_shares * Decimal("10000") * unit_nav


def sync_nav_daily(
    session: Session,
    share_id: int,
    records: list[SseNavRecord],
    collected_at: datetime,
    source_url: str,
) -> None:
    for record in records:
        business_time = datetime.combine(record.nav_date, time.min, tzinfo=ASIA_SHANGHAI)
        values = {
            "unit_nav": record.unit_nav,
            "accumulated_nav": None,
            "source_url": source_url,
            "source_time": business_time,
            "effective_from": business_time,
            "collected_at": collected_at,
            "quality_status": "verified",
        }
        statement = insert(NavDaily).values(
            fund_share_class_id=share_id,
            nav_date=record.nav_date,
            **values,
        )
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_nav_daily_share_date",
                set_=values,
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
    records: list[SseNavRecord],
    collected_at: datetime,
    source_url: str,
) -> None:
    for metric in calculate_return_metrics(records):
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
    row: dict[str, str],
    trade_date: date,
    collected_at: datetime,
) -> None:
    business_time = datetime.combine(trade_date, time.min, tzinfo=ASIA_SHANGHAI)
    values = quote_values(row, collected_at)
    if values["close_price"] is None:
        raise RuntimeError(f"SZSE quote lacked a close price on {trade_date}")
    values.update({"source_time": business_time, "effective_from": business_time})
    statement = insert(MarketQuote).values(
        fund_listing_id=listing_id,
        trade_date=trade_date,
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
    scale_date: date,
    scale_wan_shares: Decimal,
    unit_nav: Decimal,
    collected_at: datetime,
) -> None:
    business_time = datetime.combine(scale_date, time.min, tzinfo=ASIA_SHANGHAI)
    amount_cny = estimated_scale_cny(scale_wan_shares, unit_nav)
    existing = session.scalar(
        select(FundScale)
        .where(
            FundScale.fund_product_id == product_id,
            FundScale.report_date == scale_date,
        )
        .order_by(FundScale.id.desc())
        .limit(1)
    )
    values = {
        "amount": amount_cny,
        "amount_cny": amount_cny,
        "currency": "人民币",
        "source_url": SZSE_SOURCE_URL,
        "source_time": business_time,
        "effective_from": business_time,
        "collected_at": collected_at,
        "quality_status": "estimated",
    }
    if existing is None:
        session.add(
            FundScale(
                fund_product_id=product_id,
                report_date=scale_date,
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(existing, key, value)


def select_quote_row(history: list[dict[str, str]], requested_date: date | None) -> tuple[date, dict[str, str]]:
    if not history:
        raise RuntimeError("SZSE quote history was empty")
    if requested_date is None:
        row = history[0]
        return date.fromisoformat(row["jyrq"]), row
    row = next((item for item in history if item["jyrq"] == requested_date.isoformat()), None)
    if row is None:
        raise RuntimeError(f"SZSE quote was unavailable for {requested_date}")
    return requested_date, row


def select_quote_rows(
    history: list[dict[str, str]], requested_date: date | None
) -> list[tuple[date, dict[str, str]]]:
    if requested_date is not None:
        return [select_quote_row(history, requested_date)]
    if not history:
        raise RuntimeError("SZSE quote history was empty")
    return [(date.fromisoformat(row["jyrq"]), row) for row in history]


def run_sync(
    *, trade_date: date | None = None, dry_run: bool = False
) -> SzseDetailStats:
    rows, list_snapshot_date = fetch_szse_funds()
    scale_by_ticker = {row["sys_key"]: row for row in rows}
    collected_at = datetime.now(UTC)
    headers = {"Referer": SZSE_SOURCE_URL, "User-Agent": "index-fund-comparator/0.1"}
    transport = httpx.HTTPTransport(retries=3)
    funds = quotes = nav_rows = scales = 0
    failures: list[str] = []

    with get_session_factory()() as session, httpx.Client(
        trust_env=False,
        timeout=httpx.Timeout(30, connect=10),
        headers=headers,
        transport=transport,
    ) as client:
        targets = session.execute(
            select(
                FundListing,
                FundShareClass.id.label("share_id"),
                FundProduct.id.label("product_id"),
                FundProduct.exact_benchmark_id.label("index_definition_id"),
            )
            .join(FundShareClass, FundShareClass.id == FundListing.fund_share_class_id)
            .join(FundProduct, FundProduct.id == FundShareClass.fund_product_id)
            .join(IndexDefinition, IndexDefinition.id == FundProduct.exact_benchmark_id)
            .where(
                FundListing.exchange == "深交所",
                FundListing.status == "listed",
                FundShareClass.status == "active",
                FundProduct.status == "active",
            )
            .order_by(FundListing.ticker)
        ).all()
        if not targets:
            raise RuntimeError("No active target SZSE listings found; run script C first")

        for listing, share_id, product_id, index_definition_id in targets:
            ticker = listing.ticker
            try:
                quote_history = fetch_quote_history(client, ticker)
                quote_rows = select_quote_rows(quote_history, trade_date)
                szse_nav_records, _ = fetch_nav_records(client, ticker)
                eid_nav_records, nav_source_url = fetch_eid_nav_records(
                    client, ticker, list_snapshot_date
                )
                nav_records = merge_nav_records(eid_nav_records, szse_nav_records)

                scale_row = scale_by_ticker.get(ticker)
                scale_wan_shares = decimal_or_none(scale_row.get("dqgm")) if scale_row else None
                raw_scale_date = scale_row.get("scale_date") if scale_row else None
                scale_date = date.fromisoformat(raw_scale_date) if raw_scale_date else list_snapshot_date
                scale_nav = latest_nav_on_or_before(nav_records, scale_date)

                with session.begin_nested():
                    for resolved_trade_date, quote_row in quote_rows:
                        sync_quote(
                            session,
                            listing.id,
                            quote_row,
                            resolved_trade_date,
                            collected_at,
                        )
                    sync_nav_daily(session, share_id, nav_records, collected_at, nav_source_url)
                    sync_return_metrics(
                        session,
                        share_id,
                        index_definition_id,
                        load_nav_records(session, share_id),
                        collected_at,
                        nav_source_url,
                    )
                    if scale_wan_shares is not None and scale_nav is not None:
                        sync_scale(
                            session,
                            product_id,
                            scale_date,
                            scale_wan_shares,
                            scale_nav,
                            collected_at,
                        )
                funds += 1
                quotes += len(quote_rows)
                nav_rows += len(nav_records)
                scales += int(scale_wan_shares is not None and scale_nav is not None)
            except (httpx.HTTPError, RuntimeError, ValueError, SQLAlchemyError) as exc:
                failures.append(f"{ticker}: {exc}")

        if funds == 0:
            session.rollback()
            details = "; ".join(failures[:3])
            raise RuntimeError(f"SZSE detail sync produced no results: {details}")
        if dry_run:
            session.rollback()
        else:
            session.commit()

    for failure in failures:
        logger.warning("SZSE detail sync warning: %s", failure)
    return SzseDetailStats(funds, quotes, nav_rows, scales, tuple(failures))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync target SZSE ETF quotes, NAV, estimated scale, and returns"
    )
    parser.add_argument("--date", type=date.fromisoformat, help="trade date in YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    stats = run_sync(trade_date=args.date, dry_run=args.dry_run)
    action = "validated" if args.dry_run else "synced"
    print(
        f"SZSE target ETF details {action}: {stats.funds} funds, {stats.quotes} quotes, "
        f"{stats.nav_rows} NAV rows, {stats.scales} scales, "
        f"{len(stats.failures)} warnings"
    )


if __name__ == "__main__":
    main()
