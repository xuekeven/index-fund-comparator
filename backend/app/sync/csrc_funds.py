import argparse
import html
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, unquote, urljoin
from zoneinfo import ZoneInfo

import httpx
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_session_factory
from app.database_models import FundProduct, FundShareClass, NavDaily
from app.sync.sse_funds import ensure_index_master_data


CSRC_INDEX_PAGE_URL = "https://www.csrc.gov.cn/csrc/c101900/c1029655/content.shtml"
EID_BASE_URL = "http://eid.csrc.gov.cn/fund"
EID_VALIDATE_URL = f"{EID_BASE_URL}/disclose/validate_fund.do"
EID_DETAIL_URL = f"{EID_BASE_URL}/disclose/fund_detail.do"
EID_SEARCH_META_URL = f"{EID_BASE_URL}/disclose/publicDailyReportSearchData.json"
EID_NAV_URL = f"{EID_BASE_URL}/disclose/getPublicFundJZInfoMore.do"
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class TargetIndex:
    family_id: str
    definition_id: str
    benchmark_description: str
    investment_scopes: tuple[str, ...]


@dataclass(frozen=True)
class ProductCandidate:
    code: str
    name: str
    inception_date: date | None
    target: TargetIndex
    product_structure: str


@dataclass(frozen=True)
class FundDetail:
    fund_id: int
    code: str
    short_name: str
    full_name: str
    manager: str
    inception_date: date | None


@dataclass(frozen=True)
class NavRecord:
    code: str
    display_name: str
    share_class: str | None
    currency: str
    currency_form: str | None
    nav_date: date
    unit_nav: Decimal
    accumulated_nav: Decimal | None


@dataclass(frozen=True)
class SyncStats:
    products: int
    shares: int
    nav_rows: int
    failures: tuple[str, ...] = ()


CSI_500 = TargetIndex(
    "csi-500",
    "csi-500-price-cny",
    "中证500价格指数（依据基金名称归类，精确合同口径待核验）",
    ("境内",),
)
SP_500 = TargetIndex(
    "sp-500",
    "sp-500-price-cny",
    "标普500指数（人民币折算及收益口径待基金合同核验）",
    ("QDII",),
)
NASDAQ_100 = TargetIndex(
    "nasdaq-100",
    "nasdaq-100-price-cny",
    "纳斯达克100指数（人民币折算及收益口径待基金合同核验）",
    ("QDII",),
)

CSI_EXCLUDED_TOKENS = (
    "增强", "量化", "优选", "智选", "行业中性", "低波", "等权", "质量",
    "成长", "价值", "基本面", "ESG", "信息", "自由现金流", "策略",
)
US_EXCLUDED_TOKENS = ("等权", "低波", "质量", "增强", "策略", "科技", "生物")


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")").upper()


def is_exchange_or_lof_code(code: str) -> bool:
    return code.startswith(("15", "16", "50", "51", "52", "56", "58"))


def classify_product(name: str) -> tuple[TargetIndex, str] | None:
    normalized = normalize_name(name)
    if "LOF" in normalized or ("ETF" in normalized and "联接" not in normalized):
        return None
    structure = (
        "ETF联接基金"
        if "ETF" in normalized and "联接" in normalized
        else "普通开放式指数基金"
    )
    if "中证500" in normalized:
        if any(token.upper() in normalized for token in CSI_EXCLUDED_TOKENS):
            return None
        return CSI_500, structure
    if "标普500" in normalized:
        if any(token.upper() in normalized for token in US_EXCLUDED_TOKENS):
            return None
        return SP_500, structure
    if any(token in normalized for token in ("纳斯达克100", "纳指100")):
        if any(token.upper() in normalized for token in US_EXCLUDED_TOKENS):
            return None
        return NASDAQ_100, structure
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def snapshot_date_from_url(url: str) -> date:
    match = re.search(r"(20\d{6})", unquote(url))
    if match is None:
        raise RuntimeError("CSRC product index URL did not contain a snapshot date")
    return datetime.strptime(match.group(1), "%Y%m%d").date()


def parse_product_index(
    content: bytes, *, fallback_snapshot_date: date | None = None
) -> tuple[list[ProductCandidate], date]:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    title = str(sheet.cell(1, 1).value or "")
    snapshot_match = re.search(r"截至\s*(\d{8})", title)
    if snapshot_match is None and fallback_snapshot_date is None:
        raise RuntimeError("CSRC product index did not contain a snapshot date")
    snapshot_date = (
        datetime.strptime(snapshot_match.group(1), "%Y%m%d").date()
        if snapshot_match
        else fallback_snapshot_date
    )
    assert snapshot_date is not None

    candidates: list[ProductCandidate] = []
    for row in sheet.iter_rows(min_row=3, values_only=True):
        raw_code, raw_name = row[1], row[2]
        if raw_code in (None, "") or raw_name in (None, ""):
            continue
        code = str(raw_code).strip()
        if code.isdigit():
            code = code.zfill(6)
        if not re.fullmatch(r"\d{6}", code):
            continue
        if is_exchange_or_lof_code(code):
            continue
        name = str(raw_name).strip()
        classified = classify_product(name)
        if classified is None:
            continue
        target, structure = classified
        candidates.append(
            ProductCandidate(
                code, name, _as_date(row[3]), target, structure
            )
        )
    return candidates, snapshot_date


def extract_index_download_url(page_html: str) -> str:
    links = re.findall(
        r'href=["\']([^"\']+\.xlsx(?:\?[^"\']*)?)["\']', page_html, re.I
    )
    if not links:
        raise RuntimeError("CSRC product index page did not contain an XLSX download")
    return urljoin(CSRC_INDEX_PAGE_URL, html.unescape(links[-1]))


def fetch_product_index(client: httpx.Client) -> tuple[bytes, str]:
    page = client.get(CSRC_INDEX_PAGE_URL)
    page.raise_for_status()
    download_url = extract_index_download_url(page.text)
    response = client.get(download_url)
    response.raise_for_status()
    return response.content, download_url


def _clean_html_cell(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\s+", " ", text).strip()


def _detail_field(page_html: str, label: str) -> str:
    pattern = rf">\s*{re.escape(label)}\s*</td>\s*<td[^>]*>(.*?)</td>"
    match = re.search(pattern, page_html, re.I | re.S)
    return _clean_html_cell(match.group(1)) if match else ""


def parse_fund_detail(fund_id: int, page_html: str) -> FundDetail:
    title_match = re.search(
        r'class=["\']title_tu["\'][^>]*>(.*?)</td>', page_html, re.I | re.S
    )
    heading = _clean_html_cell(title_match.group(1)) if title_match else ""
    heading_match = re.match(r"(.+?)\((\d{6})\)$", heading)
    code = _detail_field(page_html, "基金代码")
    short_name = heading_match.group(1) if heading_match else ""
    if not code and heading_match:
        code = heading_match.group(2)
    full_name = _detail_field(page_html, "基金名称") or short_name
    manager = _detail_field(page_html, "基金管理人")
    inception_date = _as_date(_detail_field(page_html, "基金合同生效日期"))
    if not all((code, full_name, manager)):
        raise RuntimeError(f"EID detail page was incomplete for fundId={fund_id}")
    return FundDetail(
        fund_id, code, short_name or full_name, full_name, manager, inception_date
    )


def validate_fund_code(client: httpx.Client, code: str) -> int:
    response = client.post(EID_VALIDATE_URL, data={"cFundCode": code})
    response.raise_for_status()
    payload = response.json()
    if not payload.get("isSuccess") or not payload.get("fundId"):
        raise RuntimeError(f"EID did not recognize fund code {code}")
    return int(payload["fundId"])


def fetch_fund_detail(client: httpx.Client, fund_id: int) -> FundDetail:
    response = client.get(EID_DETAIL_URL, params={"fundId": fund_id})
    response.raise_for_status()
    return parse_fund_detail(fund_id, response.text)


def fetch_max_valuation_date(client: httpx.Client) -> date:
    response = client.post(EID_SEARCH_META_URL, data={"reportTypeStatus": "01"})
    response.raise_for_status()
    value = _as_date(response.json().get("maxValuationDate"))
    if value is None:
        raise RuntimeError("EID did not provide maxValuationDate")
    return value


def discovery_name(name: str) -> str:
    value = name.strip()
    value = re.sub(
        r"([A-Z])(?=(?:人民币|美元(?:现汇|现钞)?)?(?:\s*\([^)]*\))?$)",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"(?:人民币|美元(?:现汇|现钞)?)\s*$", "", value)
    return value.strip()


def nav_query_data(name: str, start_date: date, end_date: date) -> str:
    data = [
        {"name": "sEcho", "value": 1},
        {"name": "iColumns", "value": 5},
        {"name": "sColumns", "value": ""},
        {"name": "iDisplayStart", "value": 0},
        {"name": "iDisplayLength", "value": 500},
        {"name": "fundType", "value": "all"},
        {"name": "fundCompanyShortName", "value": ""},
        {"name": "fundCode", "value": ""},
        {"name": "fundName", "value": quote(discovery_name(name), safe="")},
        {"name": "startDate", "value": start_date.isoformat()},
        {"name": "endDate", "value": end_date.isoformat()},
    ]
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result > 0 else None


def share_identity(display_name: str) -> tuple[str | None, str, str | None]:
    compact = normalize_name(display_name)
    currency = "美元" if "美元" in compact else "人民币"
    currency_form = "现汇" if "现汇" in compact else "现钞" if "现钞" in compact else None
    for pattern in (
        r"(?:人民币|美元(?:现汇|现钞)?)?([A-Z])$",
        r"([A-Z])(?:人民币|美元(?:现汇|现钞)?)$",
    ):
        match = re.search(pattern, compact)
        if match:
            return match.group(1), currency, currency_form
    return None, currency, currency_form


def parse_nav_rows(rows: list[dict[str, Any]], fund_id: int) -> list[NavRecord]:
    records: dict[tuple[str, date], NavRecord] = {}
    for row in rows:
        if str((row.get("fund") or {}).get("idStr")) != str(fund_id):
            continue
        code = str(row.get("code") or "").strip()
        nav_date = _as_date(row.get("valuationDate"))
        unit_nav = _decimal(row.get("shareNetValue"))
        if not re.fullmatch(r"\d{6}", code) or nav_date is None or unit_nav is None:
            continue
        display_name = str(row.get("shortName") or code).strip()
        share_class, currency, currency_form = share_identity(display_name)
        records[(code, nav_date)] = NavRecord(
            code,
            display_name,
            share_class,
            currency,
            currency_form,
            nav_date,
            unit_nav,
            _decimal(row.get("totalNetValue")),
        )
    return sorted(records.values(), key=lambda item: (item.code, item.nav_date))


def fetch_nav_records(
    client: httpx.Client, fund_id: int, name: str, end_date: date
) -> list[NavRecord]:
    response = client.get(
        EID_NAV_URL,
        params={
            "aoData": nav_query_data(
                name, end_date - timedelta(days=45), end_date
            )
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is False:
        raise RuntimeError(str(payload.get("message") or "EID NAV query failed"))
    return parse_nav_rows(payload.get("aaData") or [], fund_id)


def sync_fund(
    session: Session,
    candidate: ProductCandidate,
    detail: FundDetail,
    nav_records: list[NavRecord],
    snapshot_time: datetime,
    collected_at: datetime,
) -> tuple[int, int]:
    canonical_code = f"csrc:{detail.fund_id}"
    product_values = {
        "name": detail.full_name,
        "fund_company": detail.manager,
        "product_structure": candidate.product_structure,
        "trading_venue": "仅场外",
        "investment_scopes": list(candidate.target.investment_scopes),
        "tracking_method": "被动指数",
        "exact_benchmark_id": candidate.target.definition_id,
        "benchmark_description": candidate.target.benchmark_description,
        "inception_date": detail.inception_date or candidate.inception_date,
        "source_url": f"{EID_DETAIL_URL}?fundId={detail.fund_id}",
        "source_time": snapshot_time,
        "effective_from": snapshot_time,
        "collected_at": collected_at,
        "quality_status": "verified",
    }
    statement = insert(FundProduct).values(
        canonical_code=canonical_code, **product_values
    )
    session.execute(
        statement.on_conflict_do_update(
            constraint="uq_fund_product_canonical_code",
            set_={**product_values, "updated_at": collected_at},
        )
    )
    product_id = session.scalar(
        select(FundProduct.id).where(FundProduct.canonical_code == canonical_code)
    )
    if product_id is None:
        raise RuntimeError(f"Product upsert failed for {candidate.code}")

    share_ids: dict[str, int] = {}
    latest_by_code: dict[str, NavRecord] = {}
    for record in nav_records:
        previous = latest_by_code.get(record.code)
        if previous is None or record.nav_date > previous.nav_date:
            latest_by_code[record.code] = record
    for code, record in latest_by_code.items():
        share_values = {
            "fund_product_id": product_id,
            "display_name": record.display_name,
            "share_class": record.share_class,
            "currency": record.currency,
            "currency_form": record.currency_form,
            "inception_date": candidate.inception_date if code == candidate.code else None,
            "source_url": EID_NAV_URL,
            "source_time": datetime.combine(
                record.nav_date, time.min, tzinfo=ASIA_SHANGHAI
            ),
            "effective_from": snapshot_time,
            "collected_at": collected_at,
            "quality_status": "verified",
        }
        share_statement = insert(FundShareClass).values(code=code, **share_values)
        session.execute(
            share_statement.on_conflict_do_update(
                index_elements=[FundShareClass.code],
                set_={**share_values, "updated_at": collected_at},
            )
        )
        share_id = session.scalar(
            select(FundShareClass.id).where(FundShareClass.code == code)
        )
        if share_id is None:
            raise RuntimeError(f"Share upsert failed for {code}")
        share_ids[code] = share_id

    for record in nav_records:
        values = {
            "unit_nav": record.unit_nav,
            "accumulated_nav": record.accumulated_nav,
            "source_url": EID_NAV_URL,
            "source_time": datetime.combine(
                record.nav_date, time.min, tzinfo=ASIA_SHANGHAI
            ),
            "effective_from": datetime.combine(
                record.nav_date, time.min, tzinfo=ASIA_SHANGHAI
            ),
            "collected_at": collected_at,
            "quality_status": "verified",
        }
        nav_statement = insert(NavDaily).values(
            fund_share_class_id=share_ids[record.code],
            nav_date=record.nav_date,
            **values,
        )
        session.execute(
            nav_statement.on_conflict_do_update(
                constraint="uq_nav_daily_share_date", set_=values
            )
        )
    return len(share_ids), len(nav_records)


def run_sync(*, dry_run: bool = False, limit: int | None = None) -> SyncStats:
    headers = {"User-Agent": "index-fund-comparator/0.1"}
    transport = httpx.HTTPTransport(retries=2)
    with httpx.Client(
        timeout=httpx.Timeout(20, connect=10),
        headers=headers,
        transport=transport,
    ) as client:
        content, index_url = fetch_product_index(client)
        candidates, snapshot_date = parse_product_index(
            content, fallback_snapshot_date=snapshot_date_from_url(index_url)
        )
        if limit is not None:
            candidates = candidates[:limit]
        max_nav_date = fetch_max_valuation_date(client)
        snapshot_time = datetime.combine(
            snapshot_date, time.min, tzinfo=ASIA_SHANGHAI
        )
        collected_at = datetime.now(UTC)
        products = shares = nav_rows = 0
        failures: list[str] = []
        with get_session_factory()() as session:
            ensure_index_master_data(session, snapshot_time, source_url=index_url)
            for candidate in candidates:
                try:
                    with session.begin_nested():
                        fund_id = validate_fund_code(client, candidate.code)
                        detail = fetch_fund_detail(client, fund_id)
                        records = fetch_nav_records(
                            client,
                            fund_id,
                            detail.short_name or candidate.name,
                            max_nav_date,
                        )
                        if not records:
                            records = fetch_nav_records(
                                client, fund_id, candidate.name, max_nav_date
                            )
                        if not records:
                            raise RuntimeError("no recent valid NAV/share rows")
                        synced_shares, synced_nav = sync_fund(
                            session,
                            candidate,
                            detail,
                            records,
                            snapshot_time,
                            collected_at,
                        )
                    products += 1
                    shares += synced_shares
                    nav_rows += synced_nav
                except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                    failures.append(f"{candidate.code} {candidate.name}: {exc}")
            if products == 0:
                session.rollback()
                raise RuntimeError("CSRC sync produced no products")
            if dry_run:
                session.rollback()
            else:
                session.commit()
    return SyncStats(products, shares, nav_rows, tuple(failures))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync target off-exchange funds and NAV from CSRC EID"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="validate without committing"
    )
    parser.add_argument(
        "--limit", type=int, help="process only the first N candidates"
    )
    args = parser.parse_args()
    stats = run_sync(dry_run=args.dry_run, limit=args.limit)
    action = "validated" if args.dry_run else "synced"
    print(
        f"CSRC off-exchange funds {action}: {stats.products} products, "
        f"{stats.shares} shares, {stats.nav_rows} NAV rows, "
        f"{len(stats.failures)} failures"
    )
    for failure in stats.failures:
        print(f"WARNING {failure}")


if __name__ == "__main__":
    main()
