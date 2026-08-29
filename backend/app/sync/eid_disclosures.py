import html
import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import urljoin

import httpx
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database_models import FeeHistory


PRODUCT_SUMMARY_LABEL = "基金产品资料概要"


@dataclass(frozen=True)
class DisclosureDocument:
    title: str
    url: str


def clean_html_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\s+", " ", text).strip()


def disclosure_documents(
    page_html: str,
    title_token: str,
    *,
    base_url: str,
) -> list[DisclosureDocument]:
    documents: list[DisclosureDocument] = []
    seen: set[str] = set()
    for href, raw_title in re.findall(
        r'href=["\']([^"\']*instance_show_pdf_id\.do\?instanceid=\d+)["\'][^>]*>(.*?)</a>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title = clean_html_text(raw_title)
        if title_token not in title:
            continue
        url = urljoin(base_url, html.unescape(href))
        if url in seen:
            continue
        seen.add(url)
        documents.append(DisclosureDocument(title=title, url=url))
    return documents


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def fetch_disclosure_text(
    client: httpx.Client,
    document: DisclosureDocument,
) -> str:
    response = client.get(document.url)
    response.raise_for_status()
    return extract_pdf_text(response.content)


def parse_fee_rates(
    text: str,
    *,
    include_sales_service: bool = False,
) -> dict[str, Decimal]:
    compact = re.sub(r"\s+", "", text)
    labels = {
        "management": "管理费",
        "custody": "托管费",
    }
    if include_sales_service:
        labels["sales_service"] = "销售服务费"
    rates: dict[str, Decimal] = {}
    for fee_type, label in labels.items():
        match = re.search(
            rf"{label}.{{0,400}}?([0-9]+(?:\.[0-9]+)?)%",
            compact,
        )
        if match:
            rates[fee_type] = Decimal(match.group(1))
    if "management" not in rates or "custody" not in rates:
        raise RuntimeError(
            "Fund product summary did not contain management and custody rates"
        )
    if include_sales_service:
        rates.setdefault("sales_service", Decimal("0"))
    return rates


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
                tier_description=(
                    "证监会基金产品资料概要当前费率；文件未提供原始生效日期"
                ),
                effective_from=collected_at,
                source_url=source_url,
                source_time=collected_at,
                collected_at=collected_at,
                quality_status="verified",
            )
        )
