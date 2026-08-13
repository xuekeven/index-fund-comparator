import argparse
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import FundListing, MarketQuote
from app.sync.sse_funds import SSE_SOURCE_URL


SSE_QUERY_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_DAILY_QUOTE_SQL_ID = "COMMON_SSE_CP_GPJCTPZ_GPLB_CJGK_MRGK_C"


def fetch_quote(client: httpx.Client, ticker: str, trade_date: date) -> dict[str, Any] | None:
    response = client.get(
        SSE_QUERY_URL,
        params={
            "sqlId": SSE_DAILY_QUOTE_SQL_ID,
            "SEC_CODE": ticker,
            "TX_DATE": trade_date.isoformat(),
        },
    )
    response.raise_for_status()
    rows = response.json().get("result") or []
    return rows[0] if rows else None


def decimal_or_none(value: Any, *, multiplier: Decimal = Decimal("1")) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    return Decimal(str(value)) * multiplier


def quote_values(row: dict[str, Any], collected_at: datetime) -> dict[str, Any]:
    return {
        "open_price": decimal_or_none(row.get("OPEN_PRICE")),
        "high_price": decimal_or_none(row.get("HIGH_PRICE")),
        "low_price": decimal_or_none(row.get("LOW_PRICE")),
        "close_price": decimal_or_none(row.get("CLOSE_PRICE")),
        # The official page labels these fields as 万份 and 万元.
        "volume": decimal_or_none(row.get("TRADE_VOL"), multiplier=Decimal("10000")),
        "turnover_amount": decimal_or_none(
            row.get("TRADE_AMT"), multiplier=Decimal("10000")
        ),
        "source_url": SSE_SOURCE_URL,
        "source_time": collected_at,
        "collected_at": collected_at,
        "quality_status": "verified",
    }


def resolve_latest_trade_date(client: httpx.Client, ticker: str, today: date) -> date:
    candidate = today - timedelta(days=1)
    for _ in range(12):
        if candidate.weekday() < 5 and fetch_quote(client, ticker, candidate) is not None:
            return candidate
        candidate -= timedelta(days=1)
    raise RuntimeError(f"No recent SSE quote found for {ticker}")


def sync_quotes(
    session: Session,
    client: httpx.Client,
    trade_date: date,
    collected_at: datetime,
) -> tuple[int, list[str]]:
    listings = session.execute(
        select(FundListing).where(FundListing.exchange == "上交所", FundListing.status == "listed")
    ).scalars()
    synced = 0
    missing: list[str] = []
    for listing in listings:
        row = fetch_quote(client, listing.ticker, trade_date)
        if row is None or row.get("CLOSE_PRICE") in (None, "", "-"):
            missing.append(listing.ticker)
            continue
        values = quote_values(row, collected_at)
        statement = insert(MarketQuote).values(
            fund_listing_id=listing.id,
            trade_date=trade_date,
            **values,
        )
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_market_quote_listing_date",
                set_=values,
            )
        )
        synced += 1
    return synced, missing


def run_sync(*, trade_date: date | None = None, dry_run: bool = False) -> tuple[date, int, list[str]]:
    collected_at = datetime.now(UTC)
    headers = {
        "Referer": SSE_SOURCE_URL,
        "User-Agent": "index-fund-comparator/0.1",
    }
    with httpx.Client(trust_env=False, timeout=30, headers=headers) as client:
        if trade_date is None:
            with get_session_factory()() as lookup_session:
                probe_ticker = lookup_session.scalar(
                    select(FundListing.ticker)
                    .where(FundListing.exchange == "上交所", FundListing.status == "listed")
                    .order_by(FundListing.ticker)
                    .limit(1)
                )
            if probe_ticker is None:
                raise RuntimeError("No active SSE listings found; run the master-data sync first")
            trade_date = resolve_latest_trade_date(client, probe_ticker, collected_at.date())

        with get_session_factory()() as session:
            count, missing = sync_quotes(session, client, trade_date, collected_at)
            if dry_run:
                session.rollback()
            else:
                session.commit()
    return trade_date, count, missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync official SSE daily ETF quotes")
    parser.add_argument("--date", type=date.fromisoformat, help="trade date in YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    trade_date, count, missing = run_sync(trade_date=args.date, dry_run=args.dry_run)
    action = "validated" if args.dry_run else "synced"
    print(f"SSE daily quotes {action}: {count} for {trade_date.isoformat()}")
    if missing:
        print(f"Missing quotes ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
