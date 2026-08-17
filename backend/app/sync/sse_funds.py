import argparse
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import (
    FeeHistory,
    FundListing,
    FundProduct,
    FundShareClass,
    IndexDefinition,
    IndexFamily,
    NavDaily,
)


SSE_LIST_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_SOURCE_URL = "https://etf.sse.com.cn/fundlist/"
SSE_FUND_BASE_INFO_SQL_ID = "COMMON_JJZWZ_JJLB_JJXQ_JBXX_C"
SSE_FUND_NAV_URL = "https://yunhq.sse.com.cn:32042/v1/sh1/dayk"
SSE_USER_AGENT = "index-fund-comparator/0.1"
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class TargetIndex:
    family_id: str
    definition_id: str
    official_names: tuple[str, ...]
    excluded_name_tokens: tuple[str, ...] = ()
    investment_scopes: tuple[str, ...] = ("境内",)


@dataclass(frozen=True)
class SseNavRecord:
    code: str
    nav_date: date
    unit_nav: Decimal


TARGETS = (
    TargetIndex(
        family_id="csi-500",
        definition_id="csi-500-price-cny",
        official_names=("中证小盘500指数", "中证500指数"),
        excluded_name_tokens=("增强", "低波", "等权", "质量", "价值", "成长", "现金流", "信息"),
    ),
    TargetIndex(
        family_id="sp-500",
        definition_id="sp-500-price-cny",
        official_names=("标准普尔500指数", "标普500指数"),
        investment_scopes=("QDII",),
    ),
    TargetIndex(
        family_id="nasdaq-100",
        definition_id="nasdaq-100-price-cny",
        official_names=("纳斯达克100指数", "纳斯达克-100指数"),
        investment_scopes=("QDII",),
    ),
)


def sse_detail_url(fund_code: str, category: str | None = None) -> str:
    url = (
        "https://etf.sse.com.cn/fundlist/funddetail/index.shtml"
        f"?code={fund_code}"
    )
    return f"{url}&category={category}" if category else url


def fetch_sse_funds() -> list[dict[str, Any]]:
    params = {
        "isPagination": "true",
        "sqlId": "COMMON_JJZWZ_JJLB_L",
        "pageHelp.pageSize": "2000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.endPage": "1",
        "CATEGORY": "F000",
        "type": "inParams",
    }
    with httpx.Client(trust_env=False, timeout=30) as client:
        response = client.get(
            SSE_LIST_URL,
            params=params,
            headers={"Referer": SSE_SOURCE_URL, "User-Agent": SSE_USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("result")
    if not isinstance(rows, list):
        raise RuntimeError("SSE response did not contain a fund list")
    return rows


def classify(row: dict[str, Any]) -> TargetIndex | None:
    index_name = str(row.get("INDEX_NAME") or "").strip()
    display_name = " ".join(
        str(row.get(key) or "")
        for key in ("FUND_ABBR", "FUND_EXPANSION_ABBR", "INDEX_NAME")
    )
    for target in TARGETS:
        if index_name not in target.official_names:
            continue
        if any(token in display_name for token in target.excluded_name_tokens):
            continue
        return target
    return None


def parse_sse_fee_rates(payload: dict[str, Any]) -> dict[str, Decimal]:
    rows = payload.get("result")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise RuntimeError("SSE fund base info response did not contain a result")

    rates: dict[str, Decimal] = {}
    for fee_type, field_name in (
        ("management", "MANAGEMENT_RATE"),
        ("custody", "TRUSTEESHIP_RATE"),
    ):
        raw_value = rows[0].get(field_name)
        if raw_value in (None, "", "-"):
            continue
        try:
            rate = Decimal(str(raw_value))
        except InvalidOperation as exc:
            raise RuntimeError(f"Invalid SSE {field_name}: {raw_value!r}") from exc
        if rate < 0:
            raise RuntimeError(f"Invalid negative SSE {field_name}: {raw_value!r}")
        rates[fee_type] = rate
    return rates


def fetch_sse_fund_fee_rates(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Decimal]]:
    matched_rows = {
        str(row["FUND_CODE"]): row
        for row in rows
        if row.get("FUND_CODE")
        if classify(row) is not None
    }
    fees_by_code: dict[str, dict[str, Decimal]] = {}
    with httpx.Client(trust_env=False, timeout=30) as client:
        for fund_code, row in matched_rows.items():
            category = str(row.get("CATEGORY") or "")
            detail_url = sse_detail_url(fund_code, category)
            response = client.get(
                SSE_LIST_URL,
                params={"sqlId": SSE_FUND_BASE_INFO_SQL_ID, "FUND_CODE": fund_code},
                headers={"Referer": detail_url, "User-Agent": SSE_USER_AGENT},
            )
            response.raise_for_status()
            fees_by_code[fund_code] = parse_sse_fee_rates(response.json())
    return fees_by_code


def parse_sse_nav_records(payload: dict[str, Any]) -> dict[str, SseNavRecord]:
    code = str(payload.get("code") or "").strip()
    rows = payload.get("kline")
    if not isinstance(rows, list):
        raise RuntimeError("SSE fund detail day-K response did not contain kline data")

    records: dict[str, SseNavRecord] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        raw_date = str(row[0]).strip()
        raw_nav = str(row[1]).strip()
        if not code or raw_nav in ("", "-") or len(raw_date) != 8:
            continue
        try:
            unit_nav = Decimal(raw_nav)
            nav_date = datetime.strptime(raw_date, "%Y%m%d").date()
        except (InvalidOperation, ValueError):
            continue
        if unit_nav <= 0:
            continue
        record = SseNavRecord(
            code=code,
            nav_date=nav_date,
            unit_nav=unit_nav,
        )
        if code not in records or record.nav_date > records[code].nav_date:
            records[code] = record
    return records


def fetch_sse_fund_navs(
    rows: list[dict[str, Any]],
) -> dict[str, SseNavRecord]:
    matched_rows = {
        str(row["FUND_CODE"]): row
        for row in rows
        if row.get("FUND_CODE")
        if classify(row) is not None
    }
    if not matched_rows:
        return {}

    records: dict[str, SseNavRecord] = {}
    with httpx.Client(trust_env=False, timeout=30) as client:
        for code, row in matched_rows.items():
            detail_url = sse_detail_url(code, str(row.get("CATEGORY") or ""))
            response = client.get(
                f"{SSE_FUND_NAV_URL}/{code}",
                params={
                    "begin": "-10",
                    "end": "-1",
                    "period": "day",
                    "select": "date,iopv,prevClose",
                },
                headers={"Referer": detail_url, "User-Agent": SSE_USER_AGENT},
            )
            response.raise_for_status()
            records.update(parse_sse_nav_records(response.json()))
    return records


def ensure_index_master_data(
    session: Session, collected_at: datetime, *, source_url: str = SSE_SOURCE_URL
) -> None:
    families = (
        {
            "id": "csi-500", "name": "中证500指数", "short_name": "中证500",
            "region": "中国内地", "currency": "人民币",
        },
        {
            "id": "sp-500", "name": "S&P 500 Index", "short_name": "标普500",
            "region": "美国", "currency": "美元",
        },
        {
            "id": "nasdaq-100", "name": "Nasdaq-100 Index", "short_name": "纳斯达克100",
            "region": "美国", "currency": "美元",
        },
    )
    for item in families:
        statement = insert(IndexFamily).values(
            **item,
            quality_status="verified",
            source_url=source_url,
            source_time=collected_at,
            collected_at=collected_at,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[IndexFamily.id],
                set_={**item, "updated_at": collected_at},
            )
        )

    definitions = (
        {
            "id": "csi-500-price-cny", "family_id": "csi-500", "name": "中证500价格指数",
            "short_name": "中证500", "provider": "中证指数有限公司", "region": "中国内地",
            "currency": "人民币", "index_code": "000905/399905", "benchmark_type": "价格指数",
            "exact_benchmark": "中证500价格指数（000905/399905）",
        },
        {
            "id": "sp-500-price-cny", "family_id": "sp-500", "name": "标普500价格指数人民币折算口径",
            "short_name": "标普500", "provider": "S&P Dow Jones Indices", "region": "美国",
            "currency": "人民币", "index_code": "SPX", "benchmark_type": "价格指数",
            "fx_adjustment": "人民币折算；具体基金合同口径仍需逐只核验",
            "exact_benchmark": "标普500价格指数（人民币折算，待逐只合同核验）",
        },
        {
            "id": "nasdaq-100-price-cny", "family_id": "nasdaq-100", "name": "纳斯达克100价格指数人民币折算口径",
            "short_name": "纳斯达克100", "provider": "Nasdaq", "region": "美国",
            "currency": "人民币", "index_code": "NDX", "benchmark_type": "价格指数",
            "fx_adjustment": "人民币折算；具体基金合同口径仍需逐只核验",
            "exact_benchmark": "纳斯达克100价格指数（人民币折算，待逐只合同核验）",
        },
    )
    for item in definitions:
        statement = insert(IndexDefinition).values(
            **item,
            quality_status="verified" if item["family_id"] == "csi-500" else "unavailable",
            source_url=source_url,
            source_time=collected_at,
            collected_at=collected_at,
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[IndexDefinition.id],
                set_={**item, "updated_at": collected_at},
            )
        )


def sync_fee_history(
    session: Session,
    share_id: int,
    rates: dict[str, Decimal],
    collected_at: datetime,
    source_url: str,
) -> None:
    for fee_type, rate in rates.items():
        current = session.scalar(
            select(FeeHistory)
            .where(
                FeeHistory.fund_share_class_id == share_id,
                FeeHistory.fee_type == fee_type,
                FeeHistory.effective_to.is_(None),
            )
            .order_by(
                FeeHistory.effective_from.desc().nullslast(),
                FeeHistory.id.desc(),
            )
            .limit(1)
        )
        if current is not None and current.rate == rate:
            current.source_url = source_url
            current.source_time = collected_at
            current.collected_at = collected_at
            current.quality_status = "verified"
            continue
        if current is not None:
            current.effective_to = collected_at
        session.add(
            FeeHistory(
                fund_share_class_id=share_id,
                fee_type=fee_type,
                rate=rate,
                rate_unit="percent",
                tier_description="上交所详情页当前费率；接口未提供原始生效日期",
                effective_from=collected_at,
                source_url=source_url,
                source_time=collected_at,
                collected_at=collected_at,
                quality_status="verified",
            )
        )


def sync_nav_daily(
    session: Session,
    share_id: int,
    record: SseNavRecord,
    collected_at: datetime,
    source_url: str,
) -> None:
    business_time = datetime.combine(
        record.nav_date, time.min, tzinfo=ASIA_SHANGHAI
    )
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


def sync_rows(
    session: Session,
    rows: list[dict[str, Any]],
    collected_at: datetime,
) -> int:
    synced = 0
    for row in rows:
        target = classify(row)
        if target is None:
            continue
        ticker = str(row["FUND_CODE"])
        display_name = str(row.get("FUND_EXPANSION_ABBR") or row.get("FUND_ABBR") or ticker)
        company = str(row.get("COMPANY_NAME") or "待核验")
        listing_date = date.fromisoformat(str(row["LISTING_DATE"])) if row.get("LISTING_DATE") else None
        quality = "verified" if target.family_id == "csi-500" else "unavailable"
        detail_url = sse_detail_url(ticker, str(row.get("CATEGORY") or ""))

        product_statement = insert(FundProduct).values(
            canonical_code=f"sse:{ticker}",
            name=display_name,
            fund_company=company,
            product_structure="ETF",
            trading_venue="仅场内",
            investment_scopes=list(target.investment_scopes),
            tracking_method="被动指数",
            exact_benchmark_id=target.definition_id,
            benchmark_description=(
                "中证500价格指数" if target.family_id == "csi-500"
                else f"{row.get('INDEX_NAME')}（人民币折算口径待基金合同核验）"
            ),
            source_url=SSE_SOURCE_URL,
            source_time=collected_at,
            collected_at=collected_at,
            quality_status=quality,
        )
        session.execute(
            product_statement.on_conflict_do_update(
                constraint="uq_fund_product_canonical_code",
                set_={
                    "name": display_name,
                    "fund_company": company,
                    "exact_benchmark_id": target.definition_id,
                    "source_url": SSE_SOURCE_URL,
                    "source_time": collected_at,
                    "collected_at": collected_at,
                    "updated_at": collected_at,
                },
            )
        )
        product_id = session.scalar(
            select(FundProduct.id).where(FundProduct.canonical_code == f"sse:{ticker}")
        )
        if product_id is None:
            raise RuntimeError(f"Product upsert failed for {ticker}")

        share_statement = insert(FundShareClass).values(
            fund_product_id=product_id,
            code=ticker,
            display_name=display_name,
            currency="人民币",
            inception_date=listing_date,
            source_url=SSE_SOURCE_URL,
            source_time=collected_at,
            collected_at=collected_at,
            quality_status=quality,
        )
        session.execute(
            share_statement.on_conflict_do_update(
                index_elements=[FundShareClass.code],
                set_={
                    "fund_product_id": product_id,
                    "display_name": display_name,
                    "source_url": SSE_SOURCE_URL,
                    "source_time": collected_at,
                    "collected_at": collected_at,
                    "updated_at": collected_at,
                },
            )
        )
        share_id = session.scalar(
            select(FundShareClass.id).where(FundShareClass.code == ticker)
        )
        if share_id is None:
            raise RuntimeError(f"Share upsert failed for {ticker}")

        listing_statement = insert(FundListing).values(
            fund_share_class_id=share_id,
            exchange="上交所",
            ticker=ticker,
            listing_name=str(row.get("FUND_ABBR") or display_name),
            listing_date=listing_date,
            source_url=detail_url,
            source_time=collected_at,
            collected_at=collected_at,
            quality_status="verified",
        )
        session.execute(
            listing_statement.on_conflict_do_update(
                constraint="uq_fund_listing_exchange_ticker",
                set_={
                    "fund_share_class_id": share_id,
                    "listing_name": str(row.get("FUND_ABBR") or display_name),
                    "listing_date": listing_date,
                    "source_url": detail_url,
                    "source_time": collected_at,
                    "collected_at": collected_at,
                    "updated_at": collected_at,
                },
            )
        )

        synced += 1
    return synced


def run_sync(*, dry_run: bool = False) -> int:
    collected_at = datetime.now(UTC)
    rows = fetch_sse_funds()
    with get_session_factory()() as session:
        ensure_index_master_data(session, collected_at)
        count = sync_rows(session, rows, collected_at)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync target ETFs from the SSE official fund list")
    parser.add_argument("--dry-run", action="store_true", help="validate without committing")
    args = parser.parse_args()
    count = run_sync(dry_run=args.dry_run)
    print(f"SSE target ETF rows {'validated' if args.dry_run else 'synced'}: {count}")


if __name__ == "__main__":
    main()
