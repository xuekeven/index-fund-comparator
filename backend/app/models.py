from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProductStructure(str, Enum):
    ETF = "ETF"
    OPEN_END_INDEX = "普通开放式指数基金"
    ETF_FEEDER = "ETF联接基金"


class TradingVenue(str, Enum):
    ON_EXCHANGE = "场内"
    OFF_EXCHANGE = "场外"


class TrackingMethod(str, Enum):
    PASSIVE = "被动指数"
    ENHANCED = "指数增强"


class DataStatus(str, Enum):
    VERIFIED = "verified"
    DELAYED = "delayed"
    ESTIMATED = "estimated"
    SAMPLE = "sample"
    UNAVAILABLE = "unavailable"


class HealthResponse(ApiModel):
    status: str
    version: str
    data_mode: str
    checked_at: datetime


class IndexSummary(ApiModel):
    id: str
    name: str
    short_name: str
    region: str
    currency: str
    exact_benchmark: str
    fund_count: int = 0
    status: DataStatus = DataStatus.SAMPLE


class MetricValue(ApiModel):
    period: str
    value: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: DataStatus = DataStatus.SAMPLE


class FundComparisonRow(ApiModel):
    id: str
    product_id: str
    code: str
    display_name: str
    fund_company: str
    index_id: str
    product_structure: ProductStructure
    trading_venue: TradingVenue
    investment_scope: list[str]
    tracking_method: TrackingMethod
    exact_benchmark: str
    share_class: str | None = None
    currency: str = "人民币"
    exchange: str | None = None
    management_fee: float | None = None
    custody_fee: float | None = None
    sales_service_fee: float | None = None
    expense_rate: float | None = None
    close_price: float | None = None
    close_date: date | None = None
    nav: float | None = None
    nav_date: date | None = None
    estimated_deviation: float | None = None
    scale_billion_cny: float | None = None
    scale_date: date | None = None
    returns: list[MetricValue]
    tracking_error_1y: float | None = None
    data_status: DataStatus = DataStatus.SAMPLE
    source_name: str | None = None
    source_url: str | None = None
    source_time: datetime | None = None
    note: str | None = None


class FundListResponse(ApiModel):
    index: IndexSummary
    items: list[FundComparisonRow]
    total: int
    last_synced_at: datetime | None = None
    generated_at: datetime
    data_mode: str


class ComparisonResponse(ApiModel):
    items: list[FundComparisonRow]
    generated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NavPoint(ApiModel):
    date: date
    value: float
    accumulated_value: float | None = None
    status: DataStatus = DataStatus.SAMPLE


class NavSeriesResponse(ApiModel):
    fund_code: str
    items: list[NavPoint]
    source_name: str | None = None
    generated_at: datetime
