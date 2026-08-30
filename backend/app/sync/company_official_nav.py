import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from time import monotonic, sleep
from typing import Any

import httpx


GF_NAV_URL = "https://www.gffunds.com.cn/apistore/JsonService"
CHINAAMC_FUND_URL = "https://www.chinaamc.com/fund/{code}/jijinfeilv_jg.shtml"
CHINAAMC_NAV_URL = "https://www.chinaamc.com/fund/{code}/zoust_all.js"
BOSERA_FUND_URL = "https://www.bosera.com/fund/{code}.html"
BOSERA_NAV_URL = "https://www.bosera.com/fund/fundHisDetail.json"
HARVEST_FUND_URL = (
    "https://www.jsfund.cn/Services/cn/jsp/product/basic.jsp"
    "?FundCode={code}&SiteID=1"
)
HARVEST_NAV_URL = "https://www.jsfund.cn/servlet/json"
HUAAN_FUND_URL = "https://www.huaan.com.cn/funds/{code}/"
HUAAN_NAV_URL = "https://www.huaan.com.cn/funddetail/selectFundayByCode.do"
CIFM_FUND_URL = "https://www.cifm.com/fund/{code}/"
CIFM_NAV_URL = "https://www.cifm.com/images/year/net_value_his365.xml"
CHINA_UNIVERSAL_FUND_URL = (
    "https://www.99fund.com/main/products/pofund/{code}/fundnav.shtml"
)
CHINA_UNIVERSAL_NAV_URL = (
    "https://static.99fund.com/productcenter/v1/new/compose/funds/single/curve/"
    "yield/start-to-end/index/collections"
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class OfficialNavRecord:
    code: str
    nav_date: date
    unit_nav: Decimal
    accumulated_nav: Decimal | None
    source_url: str


def _positive_decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return result if result > 0 else None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def _in_range(value: date, start_date: date, end_date: date) -> bool:
    return start_date <= value <= end_date


def parse_gf_nav(payload: dict[str, Any], code: str) -> list[OfficialNavRecord]:
    source_url = f"https://www.gffunds.com.cn/funds/?fundcode={code}"
    records: list[OfficialNavRecord] = []
    for row in payload.get("data") or []:
        nav_date = _parse_date(row.get("NAVDATE"))
        unit_nav = _positive_decimal(row.get("NAVUNIT"))
        if row.get("FUNDCODE") != code or nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(row.get("NAVACCUMULATED")),
                source_url,
            )
        )
    return records


def parse_chinaamc_nav(
    payload: dict[str, Any], code: str
) -> list[OfficialNavRecord]:
    dates = payload.get("ShowData") or []
    unit_values = payload.get("danweijingzhiName") or []
    accumulated_values = payload.get("leijiJingzhiName") or []
    if len(dates) != len(unit_values):
        raise RuntimeError("ChinaAMC NAV dates and values did not align")
    source_url = CHINAAMC_FUND_URL.format(code=code)
    records: list[OfficialNavRecord] = []
    for index, raw_date in enumerate(dates):
        nav_date = _parse_date(raw_date)
        unit_nav = _positive_decimal(unit_values[index])
        if nav_date is None or unit_nav is None:
            continue
        accumulated_nav = (
            _positive_decimal(accumulated_values[index])
            if index < len(accumulated_values)
            else None
        )
        records.append(
            OfficialNavRecord(
                code, nav_date, unit_nav, accumulated_nav, source_url
            )
        )
    return records


def parse_bosera_nav(payload: dict[str, Any], code: str) -> list[OfficialNavRecord]:
    if str(payload.get("retCode")) != "0":
        raise RuntimeError(str(payload.get("errMsg") or "Bosera NAV query failed"))
    source_url = BOSERA_FUND_URL.format(code=code)
    records: list[OfficialNavRecord] = []
    for row in (payload.get("data") or {}).get("resultList") or []:
        nav_date = _parse_date(row.get("date"))
        unit_nav = _positive_decimal(row.get("netValuePer"))
        if row.get("fundCode") != code or nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(row.get("totalNetValue")),
                source_url,
            )
        )
    return records


def harvest_product_id(page_html: str) -> str:
    match = re.search(
        r'id=["\']product_id["\'][^>]*value=["\'](\d+)["\']',
        page_html,
        re.I,
    )
    if match is None:
        match = re.search(
            r'value=["\'](\d+)["\'][^>]*id=["\']product_id["\']',
            page_html,
            re.I,
        )
    if match is None:
        raise RuntimeError("Harvest fund page did not contain product_id")
    return match.group(1)


def parse_harvest_nav(
    payload: dict[str, Any], code: str
) -> list[OfficialNavRecord]:
    results = payload.get("results") or []
    rows = (results[0] if results else {}).get("data") or []
    source_url = HARVEST_FUND_URL.format(code=code)
    records: list[OfficialNavRecord] = []
    for row in rows:
        nav_date = _parse_date(row.get("nav_date"))
        unit_nav = _positive_decimal(row.get("relate_price"))
        if nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(row.get("cumulative_net")),
                source_url,
            )
        )
    return records


def parse_huaan_nav(page_html: str, code: str) -> list[OfficialNavRecord]:
    source_url = HUAAN_FUND_URL.format(code=code)
    rows = re.findall(
        r'<td\s+class=["\']th1["\']>\s*(20\d{2}-\d{2}-\d{2})\s*</td>'
        r'\s*<td\s+class=["\']th2["\']>\s*([\d.]+)\s*</td>'
        r'\s*<td\s+class=["\']th2["\']>\s*([\d.]+)\s*</td>',
        page_html,
        re.I,
    )
    records: list[OfficialNavRecord] = []
    for raw_date, raw_unit, raw_accumulated in rows:
        nav_date = _parse_date(raw_date)
        unit_nav = _positive_decimal(raw_unit)
        if nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(raw_accumulated),
                source_url,
            )
        )
    return records


def huaan_page_count(page_html: str) -> int:
    match = re.search(r'<span\s+class=["\']curr["\']>\d+</span>\s*/\s*(\d+)', page_html)
    return int(match.group(1)) if match else 1


def parse_cifm_nav(content: bytes, code: str) -> list[OfficialNavRecord]:
    source_url = CIFM_FUND_URL.format(code=code)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RuntimeError("CIFM NAV XML was invalid") from exc
    records: list[OfficialNavRecord] = []
    for element in root.iter("Fund"):
        if element.attrib.get("FundCode") != code:
            continue
        nav_date = _parse_date(element.attrib.get("FundDate"))
        unit_nav = _positive_decimal(element.attrib.get("NetValue"))
        if nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(element.attrib.get("TotalNetValue")),
                source_url,
            )
        )
    return records


def parse_china_universal_nav(
    payload: dict[str, Any], code: str
) -> list[OfficialNavRecord]:
    if str(payload.get("returnCode")) != "0":
        raise RuntimeError(
            str(payload.get("returnMsg") or "China Universal NAV query failed")
        )
    source_url = CHINA_UNIVERSAL_FUND_URL.format(code=code)
    records: list[OfficialNavRecord] = []
    for row in payload.get("body") or []:
        nav_date = _parse_date(row.get("navDate"))
        unit_nav = _positive_decimal(row.get("navDisplay"))
        if row.get("fundId") != code or nav_date is None or unit_nav is None:
            continue
        records.append(
            OfficialNavRecord(
                code,
                nav_date,
                unit_nav,
                _positive_decimal(row.get("sumOfNav")),
                source_url,
            )
        )
    return records


def _deduplicate(
    records: list[OfficialNavRecord], start_date: date, end_date: date
) -> list[OfficialNavRecord]:
    by_date = {
        record.nav_date: record
        for record in records
        if _in_range(record.nav_date, start_date, end_date)
    }
    return [by_date[key] for key in sorted(by_date)]


class OfficialCompanyNavFetcher:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self._content_cache: dict[str, bytes] = {}
        self._bosera_last_request_at = 0.0

    def fetch(
        self,
        fund_company: str,
        code: str,
        start_date: date,
        end_date: date,
    ) -> list[OfficialNavRecord]:
        if end_date < start_date:
            return []
        if "广发基金" in fund_company:
            records = self._fetch_gf(code, start_date, end_date)
        elif "华夏基金" in fund_company:
            records = self._fetch_chinaamc(code)
        elif "博时基金" in fund_company:
            records = self._fetch_bosera(code, start_date, end_date)
        elif "嘉实基金" in fund_company:
            records = self._fetch_harvest(code, start_date, end_date)
        elif "华安基金" in fund_company:
            records = self._fetch_huaan(code, start_date)
        elif "摩根基金" in fund_company:
            records = self._fetch_cifm(code)
        elif "汇添富基金" in fund_company:
            records = self._fetch_china_universal(code, start_date, end_date)
        else:
            return []
        return _deduplicate(records, start_date, end_date)

    def _fetch_gf(
        self, code: str, start_date: date, end_date: date
    ) -> list[OfficialNavRecord]:
        records: list[OfficialNavRecord] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = self.client.get(
                GF_NAV_URL,
                params={
                    "service": "MarketPerformance",
                    "method": "NAV",
                    "op": "queryNAVByFundcode",
                    "fundcode": code,
                    "startdate": start_date.strftime("%Y%m%d"),
                    "enddate": end_date.strftime("%Y%m%d"),
                    "curpage": page,
                    "orderby": "NAVDATE_DESC",
                    "pagelines": 500,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("errorno")) != "20000":
                raise RuntimeError(str(payload.get("errormsg") or "GF NAV query failed"))
            records.extend(parse_gf_nav(payload, code))
            total_pages = int(payload.get("totalpages") or 1)
            page += 1
        return records

    def _fetch_chinaamc(self, code: str) -> list[OfficialNavRecord]:
        fund_url = CHINAAMC_FUND_URL.format(code=code)
        response = self.client.get(
            CHINAAMC_NAV_URL.format(code=code),
            headers={**BROWSER_HEADERS, "Referer": fund_url},
        )
        response.raise_for_status()
        return parse_chinaamc_nav(response.json(), code)

    def _fetch_bosera(
        self, code: str, start_date: date, end_date: date
    ) -> list[OfficialNavRecord]:
        records: list[OfficialNavRecord] = []
        window_start = start_date
        while window_start <= end_date:
            window_end = min(window_start + timedelta(days=360), end_date)
            page = 1
            total_pages = 1
            while page <= total_pages:
                response: httpx.Response | None = None
                for _attempt in range(3):
                    wait_seconds = 1.2 - (
                        monotonic() - self._bosera_last_request_at
                    )
                    if wait_seconds > 0:
                        sleep(wait_seconds)
                    response = self.client.post(
                        BOSERA_NAV_URL,
                        data={
                            "pageNo": page,
                            "pageSize": 10,
                            "fundCode": code,
                            "startDate": window_start.isoformat(),
                            "endDate": window_end.isoformat(),
                        },
                        headers={
                            **BROWSER_HEADERS,
                            "Referer": BOSERA_FUND_URL.format(code=code),
                            "Origin": "https://www.bosera.com",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                    )
                    self._bosera_last_request_at = monotonic()
                    if response.status_code != 403:
                        break
                assert response is not None
                response.raise_for_status()
                payload = response.json()
                records.extend(parse_bosera_nav(payload, code))
                paginator = (payload.get("data") or {}).get("paginator") or {}
                total_pages = int(paginator.get("total") or 1)
                page += 1
            window_start = window_end + timedelta(days=1)
        return records

    def _fetch_harvest(
        self, code: str, start_date: date, end_date: date
    ) -> list[OfficialNavRecord]:
        fund_url = HARVEST_FUND_URL.format(code=code)
        page_response = self.client.get(
            fund_url,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )
        page_response.raise_for_status()
        product_id = harvest_product_id(page_response.text)
        response = self.client.post(
            HARVEST_NAV_URL,
            data={
                "funcNo": "741012",
                "product_id": product_id,
                "type": 1,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "curtpage": 1,
                "numperpage": 500,
                "trans_no": "",
            },
            headers={**BROWSER_HEADERS, "Referer": fund_url},
        )
        response.raise_for_status()
        return parse_harvest_nav(response.json(), code)

    def _fetch_huaan(self, code: str, start_date: date) -> list[OfficialNavRecord]:
        fund_url = HUAAN_FUND_URL.format(code=code)
        records: list[OfficialNavRecord] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = self.client.get(
                HUAAN_NAV_URL,
                params={
                    "pageSize": 12,
                    "fd.fundInfo.isMoneyType": 0,
                    "gotoPage": page,
                    "fd.fundcode": code,
                },
                headers={**BROWSER_HEADERS, "Referer": fund_url},
            )
            response.raise_for_status()
            page_records = parse_huaan_nav(response.text, code)
            if not page_records:
                break
            records.extend(page_records)
            total_pages = huaan_page_count(response.text)
            if min(record.nav_date for record in page_records) <= start_date:
                break
            page += 1
        return records

    def _fetch_cifm(self, code: str) -> list[OfficialNavRecord]:
        if CIFM_NAV_URL not in self._content_cache:
            response = self.client.get(CIFM_NAV_URL, headers=BROWSER_HEADERS)
            response.raise_for_status()
            self._content_cache[CIFM_NAV_URL] = response.content
        return parse_cifm_nav(self._content_cache[CIFM_NAV_URL], code)

    def _fetch_china_universal(
        self, code: str, start_date: date, end_date: date
    ) -> list[OfficialNavRecord]:
        fund_url = CHINA_UNIVERSAL_FUND_URL.format(code=code)
        response = self.client.get(
            CHINA_UNIVERSAL_NAV_URL,
            params={
                "fundId": code,
                "startDate": start_date.strftime("%Y%m%d"),
                "endDate": end_date.strftime("%Y%m%d"),
            },
            headers={**BROWSER_HEADERS, "Referer": fund_url},
        )
        response.raise_for_status()
        return parse_china_universal_nav(response.json(), code)
