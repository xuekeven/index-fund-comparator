import argparse
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import FundListing, MarketQuote
from app.sync.szse_funds import SZSE_REPORT_URL, SZSE_SOURCE_URL, clean_report_value


SZSE_QUOTE_CATALOG_ID = "1815_fund_child"
logger = logging.getLogger(__name__)


def fetch_quote_history(client: httpx.Client, ticker: str) -> list[dict[str, str]]:
    response = client.get(
        SZSE_REPORT_URL,
        params={
            "SHOWTYPE": "JSON",
            "CATALOGID": SZSE_QUOTE_CATALOG_ID,
            "TABKEY": "tab1",
            "txtDm": ticker,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"SZSE quote report returned an unexpected payload for {ticker}")
    report = payload[0]
    if report.get("error"):
        raise RuntimeError(f"SZSE quote report error for {ticker}: {report['error']}")
    return [
        {
            key: clean_report_value(raw_row.get(key))
            for key in ("jyrq", "zqdm", "zqjc", "qss", "ss", "sdf", "cjje")
        }
        for raw_row in report.get("data") or []
    ]


def decimal_or_none(value: Any, *, multiplier: Decimal = Decimal("1")) -> Decimal | None:
    cleaned = str(value or "").replace(",", "").strip()
    if cleaned in ("", "-"):
        return None
    return Decimal(cleaned) * multiplier


def quote_values(row: dict[str, str], collected_at: datetime) -> dict[str, Any]:
    return {
        "close_price": decimal_or_none(row["ss"]),
        # The official report labels cjje as 万元.
        "turnover_amount": decimal_or_none(row["cjje"], multiplier=Decimal("10000")),
        "source_url": SZSE_SOURCE_URL,
        "source_time": collected_at,
        "collected_at": collected_at,
        "quality_status": "verified",
    }


def resolve_latest_trade_date(history: list[dict[str, str]], ticker: str) -> date:
    if not history:
        raise RuntimeError(f"No recent SZSE quote found for {ticker}")
    return date.fromisoformat(history[0]["jyrq"])


def sync_quotes(
    session: Session,
    client: httpx.Client,
    trade_date: date | None,
    collected_at: datetime,
) -> tuple[date, int, list[str]]:
    listings = list(
        session.execute(
            select(FundListing)
            .where(FundListing.exchange == "深交所", FundListing.status == "listed")
            .order_by(FundListing.ticker)
        ).scalars()
    )
    if not listings:
        raise RuntimeError("No active SZSE listings found; run the master-data sync first")

    histories: dict[str, list[dict[str, str]]] = {}
    resolved_date = trade_date
    missing: list[str] = []
    for listing in listings:
        try:
            history = fetch_quote_history(client, listing.ticker)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            missing.append(listing.ticker)
            logger.warning("SZSE quote sync skipped %s: %s", listing.ticker, exc)
            continue
        histories[listing.ticker] = history
        if resolved_date is None and history:
            resolved_date = resolve_latest_trade_date(history, listing.ticker)
    if resolved_date is None:
        raise RuntimeError("No recent SZSE quote date could be resolved")

    synced = 0
    for listing in listings:
        if listing.ticker not in histories:
            continue
        row = next(
            (
                item
                for item in histories[listing.ticker]
                if item["jyrq"] == resolved_date.isoformat()
            ),
            None,
        )
        if row is None or row["ss"] in ("", "-"):
            missing.append(listing.ticker)
            continue
        values = quote_values(row, collected_at)
        statement = insert(MarketQuote).values(
            fund_listing_id=listing.id,
            trade_date=resolved_date,
            **values,
        )
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_market_quote_listing_date",
                set_=values,
            )
        )
        synced += 1
    return resolved_date, synced, missing


def run_sync(
    *, trade_date: date | None = None, dry_run: bool = False
) -> tuple[date, int, list[str]]:
    collected_at = datetime.now(UTC)
    headers = {"Referer": SZSE_SOURCE_URL, "User-Agent": "index-fund-comparator/0.1"}
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(
        trust_env=False, timeout=30, headers=headers, transport=transport
    ) as client:
        with get_session_factory()() as session:
            resolved_date, count, missing = sync_quotes(
                session, client, trade_date, collected_at
            )
            if dry_run:
                session.rollback()
            else:
                session.commit()
    return resolved_date, count, missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync official SZSE daily ETF quotes")
    parser.add_argument("--date", type=date.fromisoformat, help="trade date in YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    trade_date, count, missing = run_sync(trade_date=args.date, dry_run=args.dry_run)
    action = "validated" if args.dry_run else "synced"
    print(f"SZSE daily quotes {action}: {count} for {trade_date.isoformat()}")
    if missing:
        print(f"Missing quotes ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
