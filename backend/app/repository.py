from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app.config import get_settings
from app.data.sample import FUND_ROWS, INDEX_ROWS
from app.database import get_session_factory
from app.database_models import (
    CalculatedMetric,
    FeeHistory,
    FundListing,
    FundProduct,
    FundScale,
    FundShareClass,
    IndexDefinition,
    IndexFamily,
    MarketQuote,
    NavDaily,
    SourceDocument,
)
from app.models import DataStatus, FundComparisonRow, IndexSummary, MetricValue, NavPoint


RETURN_PERIOD_LABELS = {
    "return_1m": "1月",
    "return_3m": "3月",
    "return_6m": "6月",
    "return_ytd": "今年来",
    "return_1y": "1年",
}


def calculate_operating_rate(
    management_fee: float | None, custody_fee: float | None
) -> float | None:
    if management_fee is None or custody_fee is None:
        return None
    return management_fee + custody_fee


def calculate_estimated_deviation(
    close_price: float | None,
    close_date: date | None,
    nav: float | None,
    nav_date: date | None,
) -> float | None:
    if (
        close_price is None
        or nav in (None, 0)
        or close_date is None
        or nav_date is None
        or close_date != nav_date
    ):
        return None
    return round((close_price / nav - 1) * 100, 4)


class FundRepository(ABC):
    @abstractmethod
    def list_indices(self) -> list[IndexSummary]: ...

    @abstractmethod
    def get_index(self, index_id: str) -> IndexSummary | None: ...

    @abstractmethod
    def get_last_synced_at(self, index_id: str) -> datetime | None: ...

    @abstractmethod
    def list_funds(self, index_id: str | None = None) -> list[FundComparisonRow]: ...

    @abstractmethod
    def get_fund(self, code: str) -> FundComparisonRow | None: ...

    @abstractmethod
    def get_funds(self, codes: list[str]) -> list[FundComparisonRow]: ...

    @abstractmethod
    def get_nav(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 1000,
    ) -> list[NavPoint]: ...

    @abstractmethod
    def is_ready(self) -> bool: ...


class SampleFundRepository(FundRepository):
    def __init__(self) -> None:
        self._funds = [FundComparisonRow.model_validate(row) for row in FUND_ROWS]
        counts: dict[str, int] = {}
        for fund in self._funds:
            counts[fund.index_id] = counts.get(fund.index_id, 0) + 1
        self._indices = [
            IndexSummary.model_validate({**row, "fund_count": counts.get(row["id"], 0)})
            for row in INDEX_ROWS
        ]

    def list_indices(self) -> list[IndexSummary]:
        return self._indices

    def get_index(self, index_id: str) -> IndexSummary | None:
        return next((item for item in self._indices if item.id == index_id), None)

    def get_last_synced_at(self, index_id: str) -> datetime | None:
        return None

    def list_funds(self, index_id: str | None = None) -> list[FundComparisonRow]:
        if index_id is None:
            return self._funds
        return [fund for fund in self._funds if fund.index_id == index_id]

    def get_fund(self, code: str) -> FundComparisonRow | None:
        return next((item for item in self._funds if item.code == code), None)

    def get_funds(self, codes: list[str]) -> list[FundComparisonRow]:
        funds_by_code = {fund.code: fund for fund in self._funds}
        return [funds_by_code[code] for code in codes if code in funds_by_code]

    def get_nav(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 1000,
    ) -> list[NavPoint]:
        fund = self.get_fund(code)
        if fund is None or fund.nav is None or fund.nav_date is None:
            return []

        daily_step = {
            "csi-500": 0.0018,
            "sp-500": 0.0011,
            "nasdaq-100": 0.0015,
        }.get(fund.index_id, 0.001)
        dates: list[date] = []
        cursor = fund.nav_date
        while len(dates) < 30:
            if cursor.weekday() < 5:
                dates.append(cursor)
            cursor -= timedelta(days=1)

        points = [
            NavPoint(
                date=point_date,
                value=round(fund.nav / ((1 + daily_step) ** (29 - position)), 4),
                accumulated_value=round(
                    fund.nav / ((1 + daily_step) ** (29 - position)), 4
                ),
                status="sample",
            )
            for position, point_date in enumerate(reversed(dates))
        ]
        return [
            point
            for point in points
            if (start_date is None or point.date >= start_date)
            and (end_date is None or point.date <= end_date)
        ][-limit:]

    def is_ready(self) -> bool:
        return True


class PostgresFundRepository(FundRepository):
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def list_indices(self) -> list[IndexSummary]:
        with self._session_factory() as session:
            count_subquery = (
                select(
                    IndexDefinition.family_id.label("family_id"),
                    func.count(FundShareClass.id).label("fund_count"),
                )
                .join(FundProduct, FundProduct.exact_benchmark_id == IndexDefinition.id)
                .join(FundShareClass, FundShareClass.fund_product_id == FundProduct.id)
                .where(FundProduct.status == "active", FundShareClass.status == "active")
                .group_by(IndexDefinition.family_id)
                .subquery()
            )
            rows = session.execute(
                select(IndexFamily, func.coalesce(count_subquery.c.fund_count, 0))
                .outerjoin(count_subquery, count_subquery.c.family_id == IndexFamily.id)
                .where(IndexFamily.status == "active")
                .order_by(
                    case(
                        (IndexFamily.id == "csi-500", 1),
                        (IndexFamily.id == "sp-500", 2),
                        (IndexFamily.id == "nasdaq-100", 3),
                        else_=99,
                    )
                )
            ).all()
            return [self._index_summary(family, count) for family, count in rows]

    def get_index(self, index_id: str) -> IndexSummary | None:
        with self._session_factory() as session:
            fund_count = (
                select(func.count(FundShareClass.id))
                .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
                .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
                .where(
                    IndexDefinition.family_id == IndexFamily.id,
                    FundProduct.status == "active",
                    FundShareClass.status == "active",
                )
                .correlate(IndexFamily)
                .scalar_subquery()
            )
            row = session.execute(
                select(IndexFamily, fund_count)
                .where(IndexFamily.id == index_id, IndexFamily.status == "active")
            ).one_or_none()
            if row is None:
                return None
            family, count = row
            return self._index_summary(family, count or 0)

    def get_last_synced_at(self, index_id: str) -> datetime | None:
        statements = (
            select(func.max(FundProduct.collected_at).label("collected_at"))
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(FundShareClass.collected_at).label("collected_at"))
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(FundListing.collected_at).label("collected_at"))
            .join(FundShareClass, FundListing.fund_share_class_id == FundShareClass.id)
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(NavDaily.collected_at).label("collected_at"))
            .join(FundShareClass, NavDaily.fund_share_class_id == FundShareClass.id)
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(MarketQuote.collected_at).label("collected_at"))
            .join(FundListing, MarketQuote.fund_listing_id == FundListing.id)
            .join(FundShareClass, FundListing.fund_share_class_id == FundShareClass.id)
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(FundScale.collected_at).label("collected_at"))
            .outerjoin(FundShareClass, FundScale.fund_share_class_id == FundShareClass.id)
            .join(
                FundProduct,
                or_(
                    FundScale.fund_product_id == FundProduct.id,
                    FundShareClass.fund_product_id == FundProduct.id,
                ),
            )
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(FeeHistory.collected_at).label("collected_at"))
            .join(FundShareClass, FeeHistory.fund_share_class_id == FundShareClass.id)
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
            select(func.max(CalculatedMetric.collected_at).label("collected_at"))
            .join(FundShareClass, CalculatedMetric.fund_share_class_id == FundShareClass.id)
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id),
        )
        sync_times = union_all(*statements).subquery()
        with self._session_factory() as session:
            return session.scalar(select(func.max(sync_times.c.collected_at)))

    def list_funds(self, index_id: str | None = None) -> list[FundComparisonRow]:
        with self._session_factory() as session:
            statement = self._fund_statement()
            if index_id is not None:
                statement = statement.where(IndexDefinition.family_id == index_id)
            rows = session.execute(statement.order_by(FundShareClass.code)).mappings().all()
            row_dicts = [dict(row) for row in rows]
            fees_by_share, metrics_by_share = self._load_fund_details(
                session, [row["share_id"] for row in row_dicts]
            )
            return [
                self._fund_row(
                    row,
                    fees_by_share.get(row["share_id"], {}),
                    metrics_by_share.get(row["share_id"], {}),
                )
                for row in row_dicts
            ]

    def get_fund(self, code: str) -> FundComparisonRow | None:
        funds = self.get_funds([code])
        return funds[0] if funds else None

    def get_funds(self, codes: list[str]) -> list[FundComparisonRow]:
        if not codes:
            return []
        with self._session_factory() as session:
            rows = session.execute(
                self._fund_statement().where(
                    or_(FundShareClass.code.in_(codes), FundListing.ticker.in_(codes))
                )
            ).mappings().all()
            row_dicts = [dict(row) for row in rows]
            fees_by_share, metrics_by_share = self._load_fund_details(
                session, [row["share_id"] for row in row_dicts]
            )
            funds_by_code = {
                row["ticker"] or row["code"]: self._fund_row(
                    row,
                    fees_by_share.get(row["share_id"], {}),
                    metrics_by_share.get(row["share_id"], {}),
                )
                for row in row_dicts
            }
            return [funds_by_code[code] for code in codes if code in funds_by_code]

    def get_nav(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 1000,
    ) -> list[NavPoint]:
        with self._session_factory() as session:
            share_id = session.scalar(
                select(FundShareClass.id)
                .outerjoin(FundListing, FundListing.fund_share_class_id == FundShareClass.id)
                .where(or_(FundShareClass.code == code, FundListing.ticker == code))
            )
            if share_id is None:
                return []
            statement = select(NavDaily).where(NavDaily.fund_share_class_id == share_id)
            if start_date is not None:
                statement = statement.where(NavDaily.nav_date >= start_date)
            if end_date is not None:
                statement = statement.where(NavDaily.nav_date <= end_date)
            rows = list(
                session.execute(
                    statement.order_by(NavDaily.nav_date.desc()).limit(limit)
                ).scalars()
            )
            return [
                NavPoint(
                    date=row.nav_date,
                    value=float(row.unit_nav),
                    accumulated_value=(
                        float(row.accumulated_nav) if row.accumulated_nav is not None else None
                    ),
                    status=self._status(row.quality_status),
                )
                for row in reversed(rows)
            ]

    def is_ready(self) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(1)) == 1

    @staticmethod
    def _index_summary(family: IndexFamily, count: int) -> IndexSummary:
        return IndexSummary(
            id=family.id,
            name=family.name,
            short_name=family.short_name,
            region=family.region,
            currency=family.currency,
            exact_benchmark="按各基金合同中的精确跟踪基准分组",
            fund_count=int(count),
            status=PostgresFundRepository._status(family.quality_status),
        )

    @staticmethod
    def _latest_id_subquery(model: Any, owner_column: Any, date_column: Any) -> Select[Any]:
        return (
            select(model.id)
            .where(owner_column == FundShareClass.id)
            .order_by(date_column.desc(), model.id.desc())
            .limit(1)
            .correlate(FundShareClass)
        )

    def _fund_statement(self) -> Select[Any]:
        latest_nav = aliased(NavDaily)
        latest_quote = aliased(MarketQuote)
        latest_scale = aliased(FundScale)
        source = aliased(SourceDocument)

        latest_nav_id = self._latest_id_subquery(
            NavDaily, NavDaily.fund_share_class_id, NavDaily.nav_date
        )
        latest_quote_id = (
            select(MarketQuote.id)
            .where(MarketQuote.fund_listing_id == FundListing.id)
            .order_by(MarketQuote.trade_date.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(FundListing)
        )
        latest_scale_id = (
            select(FundScale.id)
            .where(
                or_(
                    FundScale.fund_share_class_id == FundShareClass.id,
                    and_(
                        FundScale.fund_share_class_id.is_(None),
                        FundScale.fund_product_id == FundProduct.id,
                    ),
                )
            )
            .order_by(FundScale.report_date.desc(), FundScale.id.desc())
            .limit(1)
            .correlate(FundShareClass, FundProduct)
        )

        return (
            select(
                FundShareClass.id.label("share_id"),
                FundShareClass.code,
                FundShareClass.display_name,
                FundShareClass.share_class,
                FundShareClass.currency,
                FundShareClass.quality_status.label("share_quality"),
                FundShareClass.source_url.label("share_source_url"),
                FundShareClass.source_time.label("share_source_time"),
                FundProduct.id.label("product_id"),
                FundProduct.fund_company,
                FundProduct.product_structure,
                FundProduct.trading_venue,
                FundProduct.investment_scopes,
                FundProduct.tracking_method,
                FundProduct.benchmark_description,
                FundProduct.source_url.label("product_source_url"),
                FundProduct.source_time.label("product_source_time"),
                IndexDefinition.family_id.label("index_id"),
                FundListing.id.label("listing_id"),
                FundListing.exchange,
                FundListing.ticker,
                latest_nav.unit_nav.label("nav"),
                latest_nav.nav_date,
                latest_quote.close_price,
                latest_quote.trade_date.label("close_date"),
                latest_scale.amount_cny.label("scale_cny"),
                latest_scale.report_date.label("scale_date"),
                source.source_name,
                func.coalesce(
                    FundProduct.source_url, FundShareClass.source_url, source.url
                ).label("source_url"),
                func.coalesce(
                    FundShareClass.source_time, FundProduct.source_time, source.published_at
                ).label("source_time"),
            )
            .join(FundProduct, FundShareClass.fund_product_id == FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .outerjoin(FundListing, FundListing.fund_share_class_id == FundShareClass.id)
            .outerjoin(latest_nav, latest_nav.id == latest_nav_id.scalar_subquery())
            .outerjoin(latest_quote, latest_quote.id == latest_quote_id.scalar_subquery())
            .outerjoin(latest_scale, latest_scale.id == latest_scale_id.scalar_subquery())
            .outerjoin(
                source,
                source.id
                == func.coalesce(
                    FundShareClass.source_document_id, FundProduct.source_document_id
                ),
            )
            .where(FundProduct.status == "active", FundShareClass.status == "active")
        )

    @staticmethod
    def _load_fund_details(
        session: Session, share_ids: list[int]
    ) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, CalculatedMetric]]]:
        if not share_ids:
            return {}, {}

        fee_rank = func.row_number().over(
            partition_by=(FeeHistory.fund_share_class_id, FeeHistory.fee_type),
            order_by=(
                FeeHistory.effective_from.desc().nullslast(),
                FeeHistory.id.desc(),
            ),
        ).label("rank")
        latest_fees = (
            select(
                FeeHistory.fund_share_class_id.label("share_id"),
                FeeHistory.fee_type,
                FeeHistory.rate,
                fee_rank,
            )
            .where(
                FeeHistory.fund_share_class_id.in_(share_ids),
                or_(FeeHistory.effective_from.is_(None), FeeHistory.effective_from <= func.now()),
                or_(FeeHistory.effective_to.is_(None), FeeHistory.effective_to > func.now()),
            )
            .subquery()
        )
        fees_by_share: dict[int, dict[str, float]] = {}
        for share_id, fee_type, rate in session.execute(
            select(latest_fees.c.share_id, latest_fees.c.fee_type, latest_fees.c.rate)
            .where(latest_fees.c.rank == 1)
        ).all():
            fees_by_share.setdefault(share_id, {})[fee_type] = float(rate)

        metric_rank = func.row_number().over(
            partition_by=(
                CalculatedMetric.fund_share_class_id,
                CalculatedMetric.metric_code,
            ),
            order_by=(CalculatedMetric.period_end.desc(), CalculatedMetric.id.desc()),
        ).label("rank")
        latest_metric_ids = (
            select(CalculatedMetric.id.label("metric_id"), metric_rank)
            .where(CalculatedMetric.fund_share_class_id.in_(share_ids))
            .subquery()
        )
        metrics_by_share: dict[int, dict[str, CalculatedMetric]] = {}
        metrics = session.execute(
            select(CalculatedMetric)
            .join(latest_metric_ids, latest_metric_ids.c.metric_id == CalculatedMetric.id)
            .where(latest_metric_ids.c.rank == 1)
        ).scalars()
        for metric in metrics:
            metrics_by_share.setdefault(metric.fund_share_class_id, {})[
                metric.metric_code
            ] = metric
        return fees_by_share, metrics_by_share

    def _fund_row(
        self,
        row: dict[str, Any],
        fees: dict[str, float],
        latest_metrics: dict[str, CalculatedMetric],
    ) -> FundComparisonRow:

        management = fees.get("management")
        custody = fees.get("custody")
        sales_service = fees.get("sales_service")
        expense_rate = calculate_operating_rate(management, custody)
        nav = float(row["nav"]) if row["nav"] is not None else None
        close = float(row["close_price"]) if row["close_price"] is not None else None
        estimated_deviation = calculate_estimated_deviation(
            close,
            row["close_date"],
            nav,
            row["nav_date"],
        )

        returns = [
            MetricValue(
                period=label,
                value=float(metric.value) if metric.value is not None else None,
                start_date=metric.period_start,
                end_date=metric.period_end,
                status=self._status(metric.quality_status),
            )
            for code, label in RETURN_PERIOD_LABELS.items()
            if (metric := latest_metrics.get(code)) is not None
        ]
        return FundComparisonRow(
            id=f"share-{row['share_id']}",
            product_id=f"product-{row['product_id']}",
            code=row["ticker"] or row["code"],
            display_name=row["display_name"],
            fund_company=row["fund_company"],
            index_id=row["index_id"],
            product_structure=row["product_structure"],
            trading_venue="场内" if row["trading_venue"] == "仅场内" else "场外",
            investment_scope=row["investment_scopes"] or [],
            tracking_method=row["tracking_method"],
            exact_benchmark=row["benchmark_description"],
            share_class=row["share_class"],
            currency=row["currency"],
            exchange=row["exchange"],
            management_fee=management,
            custody_fee=custody,
            sales_service_fee=sales_service,
            expense_rate=expense_rate,
            close_price=close,
            close_date=row["close_date"],
            nav=nav,
            nav_date=row["nav_date"],
            estimated_deviation=estimated_deviation,
            scale_billion_cny=(
                float(row["scale_cny"]) / 100_000_000 if row["scale_cny"] is not None else None
            ),
            scale_date=row["scale_date"],
            returns=returns,
            data_status=self._status(row["share_quality"]),
            source_name=row["source_name"],
            source_url=row["source_url"],
            source_time=row["source_time"],
        )

    @staticmethod
    def _status(value: str | None) -> DataStatus:
        try:
            return DataStatus(value or "unavailable")
        except ValueError:
            return DataStatus.UNAVAILABLE


@lru_cache
def get_repository() -> FundRepository:
    settings = get_settings()
    if settings.data_mode == "database":
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required when IFC_DATA_MODE=database")
        return PostgresFundRepository()
    return SampleFundRepository()
