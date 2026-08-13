import argparse
import html
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import FundListing, FundProduct, FundShareClass, IndexDefinition
from app.sync.sse_funds import ensure_index_master_data


SZSE_REPORT_URL = "https://www.szse.cn/api/report/ShowReport/data"
SZSE_SOURCE_URL = "https://www.szse.cn/www/market/product/list/etfList/index.html"
SZSE_ETF_CATALOG_ID = "1945"
SZSE_SEARCH_TERMS = ("中证500", "标普500", "纳指", "纳斯达克100")
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class SzseTarget:
    family_id: str
    definition_id: str
    benchmark_description: str
    investment_scopes: tuple[str, ...]
    quality_status: str


CSI_500_TARGET = SzseTarget(
    family_id="csi-500",
    definition_id="csi-500-price-cny",
    benchmark_description="中证500价格指数（000905/399905）",
    investment_scopes=("境内",),
    quality_status="verified",
)
SP_500_TARGET = SzseTarget(
    family_id="sp-500",
    definition_id="sp-500-net-return-cny",
    benchmark_description="标普500净总收益指数（SPXNTR，人民币折算口径待基金合同核验）",
    investment_scopes=("QDII",),
    quality_status="unavailable",
)
NASDAQ_100_TARGET = SzseTarget(
    family_id="nasdaq-100",
    definition_id="nasdaq-100-price-cny",
    benchmark_description="纳斯达克100价格指数（NDX，人民币折算口径待基金合同核验）",
    investment_scopes=("QDII",),
    quality_status="unavailable",
)

CSI_500_EXCLUDED_TOKENS = (
    "增强",
    "成长",
    "价值",
    "低波",
    "等权",
    "质量",
    "现金流",
    "信息",
)


def clean_report_value(value: Any) -> str:
    without_tags = re.sub(r"<[^>]+>", "", str(value or ""))
    return html.unescape(without_tags).strip()


def report_params(*, page: int, search_term: str) -> dict[str, str]:
    return {
        "SHOWTYPE": "JSON",
        "CATALOGID": SZSE_ETF_CATALOG_ID,
        "TABKEY": "tab1",
        "PAGENO": str(page),
        "txtQueryKeyAndJC": search_term,
    }


def fetch_report_page(
    client: httpx.Client, *, page: int, search_term: str
) -> dict[str, Any]:
    response = client.get(SZSE_REPORT_URL, params=report_params(page=page, search_term=search_term))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("SZSE ETF report returned an unexpected payload")
    report = payload[0]
    if report.get("error"):
        raise RuntimeError(f"SZSE ETF report error: {report['error']}")
    return report


def fetch_szse_funds() -> tuple[list[dict[str, str]], date]:
    rows_by_ticker: dict[str, dict[str, str]] = {}
    snapshot_dates: list[date] = []
    headers = {"Referer": SZSE_SOURCE_URL, "User-Agent": "index-fund-comparator/0.1"}
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(
        trust_env=False, timeout=30, headers=headers, transport=transport
    ) as client:
        for search_term in SZSE_SEARCH_TERMS:
            first = fetch_report_page(client, page=1, search_term=search_term)
            metadata = first["metadata"]
            if metadata.get("subname"):
                snapshot_dates.append(date.fromisoformat(metadata["subname"]))
            page_count = int(metadata.get("pagecount") or 1)
            for page in range(1, page_count + 1):
                report = first if page == 1 else fetch_report_page(
                    client, page=page, search_term=search_term
                )
                for raw_row in report.get("data") or []:
                    row = {
                        key: clean_report_value(raw_row.get(key))
                        for key in ("sys_key", "kzjcurl", "nhzs", "dqgm", "glrmc")
                    }
                    if row["sys_key"]:
                        rows_by_ticker[row["sys_key"]] = row
    if not snapshot_dates:
        raise RuntimeError("SZSE ETF report did not provide a snapshot date")
    return list(rows_by_ticker.values()), max(snapshot_dates)


def classify(row: dict[str, str]) -> SzseTarget | None:
    name = row["kzjcurl"]
    index_code = row["nhzs"].replace(" ", "").upper()
    if index_code.startswith(("000905", "399905")):
        if any(token in name for token in CSI_500_EXCLUDED_TOKENS):
            return None
        return CSI_500_TARGET
    if index_code.startswith("SPXNTR"):
        return SP_500_TARGET
    if index_code == "NDX":
        return NASDAQ_100_TARGET
    return None


def ensure_szse_index_definitions(session: Session, source_time: datetime) -> None:
    ensure_index_master_data(session, source_time, source_url=SZSE_SOURCE_URL)
    values = {
        "id": "sp-500-net-return-cny",
        "family_id": "sp-500",
        "name": "标普500净总收益指数人民币折算口径",
        "short_name": "标普500净收益",
        "provider": "S&P Dow Jones Indices",
        "region": "美国",
        "currency": "人民币",
        "index_code": "SPXNTR",
        "benchmark_type": "净收益指数",
        "fx_adjustment": "人民币折算；具体基金合同口径仍需逐只核验",
        "exact_benchmark": "标普500净总收益指数（SPXNTR，人民币折算口径待逐只合同核验）",
        "source_url": SZSE_SOURCE_URL,
        "source_time": source_time,
        "effective_from": source_time,
        "collected_at": datetime.now(UTC),
        "quality_status": "unavailable",
    }
    statement = insert(IndexDefinition).values(**values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[IndexDefinition.id],
            set_={
                key: value
                for key, value in values.items()
                if key not in {"id", "collected_at"}
            },
        )
    )


def sync_rows(session: Session, rows: list[dict[str, str]], source_time: datetime) -> int:
    collected_at = datetime.now(UTC)
    synced = 0
    for row in rows:
        target = classify(row)
        if target is None:
            continue
        ticker = row["sys_key"]
        canonical_code = f"szse:{ticker}"
        product_values = {
            "name": row["kzjcurl"],
            "fund_company": row["glrmc"] or "待核验",
            "product_structure": "ETF",
            "trading_venue": "仅场内",
            "investment_scopes": list(target.investment_scopes),
            "tracking_method": "被动指数",
            "exact_benchmark_id": target.definition_id,
            "benchmark_description": target.benchmark_description,
            "source_url": SZSE_SOURCE_URL,
            "source_time": source_time,
            "effective_from": source_time,
            "collected_at": collected_at,
            "quality_status": target.quality_status,
        }
        product_statement = insert(FundProduct).values(
            canonical_code=canonical_code, **product_values
        )
        session.execute(
            product_statement.on_conflict_do_update(
                constraint="uq_fund_product_canonical_code",
                set_={**product_values, "updated_at": collected_at},
            )
        )
        product_id = session.scalar(
            select(FundProduct.id).where(FundProduct.canonical_code == canonical_code)
        )
        if product_id is None:
            raise RuntimeError(f"Product upsert failed for {ticker}")

        share_values = {
            "fund_product_id": product_id,
            "display_name": row["kzjcurl"],
            "currency": "人民币",
            "source_url": SZSE_SOURCE_URL,
            "source_time": source_time,
            "effective_from": source_time,
            "collected_at": collected_at,
            "quality_status": target.quality_status,
        }
        share_statement = insert(FundShareClass).values(code=ticker, **share_values)
        session.execute(
            share_statement.on_conflict_do_update(
                index_elements=[FundShareClass.code],
                set_={**share_values, "updated_at": collected_at},
            )
        )
        share_id = session.scalar(
            select(FundShareClass.id).where(FundShareClass.code == ticker)
        )
        if share_id is None:
            raise RuntimeError(f"Share upsert failed for {ticker}")

        listing_values = {
            "fund_share_class_id": share_id,
            "listing_name": row["kzjcurl"],
            "source_url": SZSE_SOURCE_URL,
            "source_time": source_time,
            "effective_from": source_time,
            "collected_at": collected_at,
            "quality_status": "verified",
        }
        listing_statement = insert(FundListing).values(
            exchange="深交所", ticker=ticker, **listing_values
        )
        session.execute(
            listing_statement.on_conflict_do_update(
                constraint="uq_fund_listing_exchange_ticker",
                set_={**listing_values, "updated_at": collected_at},
            )
        )
        synced += 1
    return synced


def run_sync(*, dry_run: bool = False) -> tuple[date, int]:
    rows, snapshot_date = fetch_szse_funds()
    source_time = datetime.combine(snapshot_date, time.min, tzinfo=ASIA_SHANGHAI)
    with get_session_factory()() as session:
        ensure_szse_index_definitions(session, source_time)
        count = sync_rows(session, rows, source_time)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return snapshot_date, count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync target ETFs from the SZSE official list")
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    snapshot_date, count = run_sync(dry_run=args.dry_run)
    action = "validated" if args.dry_run else "synced"
    print(f"SZSE target ETF rows {action}: {count} for {snapshot_date.isoformat()}")


if __name__ == "__main__":
    main()
