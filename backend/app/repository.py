from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any

from sqlalchemy import Select, and_, case, delete, func, literal, or_, select, union_all
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
    InvestmentNote,
    MarketQuote,
    NavDaily,
    SalesLimitHistory,
    SourceDocument,
    UserFundTag,
)
from app.models import (
    DataStatus,
    DataFreshness,
    FundComparisonRow,
    FundTagType,
    IndexSummary,
    InvestmentNoteCreate,
    InvestmentNoteItem,
    InvestmentNoteUpdate,
    MetricValue,
    NavPoint,
)


RETURN_PERIOD_LABELS = {
    "return_1m": "1月",
    "return_3m": "3月",
    "return_6m": "6月",
    "return_ytd": "今年来",
    "return_1y": "1年",
}
SINGLE_USER_ID = "default"
FUND_TAG_ORDER = {
    FundTagType.FAVORITE: 0,
    FundTagType.HOLDING: 1,
    FundTagType.RECURRING: 2,
}


def _normalized_note_values(
    payload: InvestmentNoteCreate | InvestmentNoteUpdate,
) -> dict[str, Any]:
    values = payload.model_dump()
    values["title"] = payload.title.strip()
    values["category"] = payload.category.value
    values["action"] = payload.action.value if payload.action else None
    for field in (
        "source_name",
        "source_url",
        "source_excerpt",
        "own_summary",
    ):
        value = values[field]
        values[field] = value.strip() if value and value.strip() else None
    values["content_markdown"] = payload.content_markdown.strip()
    for field in ("tags", "index_ids", "fund_codes"):
        values[field] = list(
            dict.fromkeys(value.strip() for value in values[field] if value.strip())
        )
    return values


def _note_item(note: InvestmentNote) -> InvestmentNoteItem:
    return InvestmentNoteItem(
        id=note.id,
        note_date=note.note_date,
        title=note.title,
        category=note.category,
        action=note.action,
        source_name=note.source_name,
        source_url=note.source_url,
        source_excerpt=note.source_excerpt,
        own_summary=note.own_summary,
        content_markdown=note.content_markdown,
        tags=list(note.tags or []),
        index_ids=list(note.index_ids or []),
        fund_codes=list(note.fund_codes or []),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def calculate_operating_rate(
    management_fee: float | None,
    custody_fee: float | None,
    sales_service_fee: float | None = None,
    comprehensive_operating_fee: float | None = None,
) -> float | None:
    if comprehensive_operating_fee is not None:
        return comprehensive_operating_fee
    if management_fee is None or custody_fee is None:
        return None
    return management_fee + custody_fee + (sales_service_fee or 0)


def calculate_estimated_deviation(
    close_price: float | None,
    close_date: date | None,
    nav: float | None,
    nav_date: date | None,
    *,
    allow_lagged_nav: bool = False,
) -> float | None:
    next_weekday = nav_date + timedelta(days=1) if nav_date is not None else None
    while next_weekday is not None and next_weekday.weekday() >= 5:
        next_weekday += timedelta(days=1)
    if (
        close_price is None
        or nav in (None, 0)
        or close_date is None
        or nav_date is None
        or (
            close_date != nav_date
            and not (allow_lagged_nav and close_date == next_weekday)
        )
    ):
        return None
    return round((close_price / nav - 1) * 100, 4)


class FundRepository(ABC):
    @abstractmethod
    def list_indices(self) -> list[IndexSummary]: ...

    @abstractmethod
    def get_index(self, index_id: str) -> IndexSummary | None: ...

    @abstractmethod
    def get_last_synced_at(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> datetime | None: ...

    @abstractmethod
    def get_data_freshness(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> DataFreshness: ...

    @abstractmethod
    def list_funds(self, index_id: str | None = None) -> list[FundComparisonRow]: ...

    @abstractmethod
    def get_fund(self, code: str) -> FundComparisonRow | None: ...

    @abstractmethod
    def get_funds(self, codes: list[str]) -> list[FundComparisonRow]: ...

    @abstractmethod
    def set_fund_tags(
        self, code: str, tags: list[FundTagType]
    ) -> list[FundTagType] | None: ...

    @abstractmethod
    def list_notes(
        self,
        query: str | None = None,
        category: str | None = None,
        year: int | None = None,
    ) -> list[InvestmentNoteItem]: ...

    @abstractmethod
    def create_note(self, payload: InvestmentNoteCreate) -> InvestmentNoteItem: ...

    @abstractmethod
    def update_note(
        self, note_id: int, payload: InvestmentNoteUpdate
    ) -> InvestmentNoteItem | None: ...

    @abstractmethod
    def delete_note(self, note_id: int) -> bool: ...

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
        now = datetime.now(UTC)
        self._notes = [
            InvestmentNoteItem(
                id=1,
                note_date=date(2026, 7, 21),
                title="加减仓",
                category="长期",
                action="加仓",
                source_name="tombkeeper（群）",
                source_excerpt="- 加仓要慢：分批低吸，确认方向\n- 清仓要快：确认结束，立即执行",
                own_summary=(
                    "QDII 基金限购且非实时交易，除非确认行情结束，"
                    "否则不要轻易卖出；场内品种更适合即时调整。"
                ),
                content_markdown="记录市场判断，也记录判断成立的条件和失效信号。",
                tags=["加减仓", "QDII"],
                index_ids=["sp-500", "nasdaq-100"],
                fund_codes=[],
                created_at=now,
                updated_at=now,
            )
        ]
        self._next_note_id = 2

    def list_indices(self) -> list[IndexSummary]:
        return self._indices

    def get_index(self, index_id: str) -> IndexSummary | None:
        return next((item for item in self._indices if item.id == index_id), None)

    def get_last_synced_at(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> datetime | None:
        return None

    def get_data_freshness(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> DataFreshness:
        return DataFreshness()

    def list_funds(self, index_id: str | None = None) -> list[FundComparisonRow]:
        if index_id is None:
            return self._funds
        return [fund for fund in self._funds if fund.index_id == index_id]

    def get_fund(self, code: str) -> FundComparisonRow | None:
        return next((item for item in self._funds if item.code == code), None)

    def get_funds(self, codes: list[str]) -> list[FundComparisonRow]:
        funds_by_code = {fund.code: fund for fund in self._funds}
        return [funds_by_code[code] for code in codes if code in funds_by_code]

    def set_fund_tags(
        self, code: str, tags: list[FundTagType]
    ) -> list[FundTagType] | None:
        normalized = sorted(set(tags), key=FUND_TAG_ORDER.__getitem__)
        for index, fund in enumerate(self._funds):
            if fund.code != code:
                continue
            self._funds[index] = fund.model_copy(update={"tags": normalized})
            return normalized
        return None

    def list_notes(
        self,
        query: str | None = None,
        category: str | None = None,
        year: int | None = None,
    ) -> list[InvestmentNoteItem]:
        normalized_query = query.strip().casefold() if query else None
        notes = [
            note
            for note in self._notes
            if (category is None or note.category.value == category)
            and (year is None or note.note_date.year == year)
            and (
                normalized_query is None
                or normalized_query
                in " ".join(
                    filter(
                        None,
                        (
                            note.title,
                            note.source_name,
                            note.source_excerpt,
                            note.own_summary,
                            note.content_markdown,
                            " ".join(note.tags),
                        ),
                    )
                ).casefold()
            )
        ]
        return sorted(notes, key=lambda note: (note.note_date, note.id), reverse=True)

    def create_note(self, payload: InvestmentNoteCreate) -> InvestmentNoteItem:
        now = datetime.now(UTC)
        note = InvestmentNoteItem(
            id=self._next_note_id,
            **_normalized_note_values(payload),
            created_at=now,
            updated_at=now,
        )
        self._next_note_id += 1
        self._notes.append(note)
        return note

    def update_note(
        self, note_id: int, payload: InvestmentNoteUpdate
    ) -> InvestmentNoteItem | None:
        for index, note in enumerate(self._notes):
            if note.id != note_id:
                continue
            updated = InvestmentNoteItem.model_validate(
                {
                    **note.model_dump(),
                    **_normalized_note_values(payload),
                    "updated_at": datetime.now(UTC),
                }
            )
            self._notes[index] = updated
            return updated
        return None

    def delete_note(self, note_id: int) -> bool:
        original_count = len(self._notes)
        self._notes = [note for note in self._notes if note.id != note_id]
        return len(self._notes) != original_count

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

    @staticmethod
    def _scoped_product_ids(
        index_id: str,
        venue: str | None,
        exchanges: tuple[str, ...],
    ) -> Select[Any]:
        product_ids = (
            select(FundProduct.id)
            .join(IndexDefinition, FundProduct.exact_benchmark_id == IndexDefinition.id)
            .where(IndexDefinition.family_id == index_id)
        )
        if venue:
            product_ids = product_ids.where(FundProduct.trading_venue == f"仅{venue}")
        if exchanges:
            product_ids = (
                product_ids
                .join(FundShareClass, FundShareClass.fund_product_id == FundProduct.id)
                .join(FundListing, FundListing.fund_share_class_id == FundShareClass.id)
                .where(FundListing.exchange.in_(exchanges))
            )
        return product_ids.distinct()

    def get_data_freshness(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> DataFreshness:
        product_ids = self._scoped_product_ids(index_id, venue, exchanges)
        statements = (
            select(
                literal("master").label("category"),
                func.max(FundProduct.collected_at).label("collected_at"),
            )
            .where(FundProduct.id.in_(product_ids)),
            select(
                literal("master").label("category"),
                func.max(FundShareClass.collected_at).label("collected_at"),
            )
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("master").label("category"),
                func.max(FundListing.collected_at).label("collected_at"),
            )
            .join(FundShareClass, FundListing.fund_share_class_id == FundShareClass.id)
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("nav").label("category"),
                func.max(NavDaily.collected_at).label("collected_at"),
            )
            .join(FundShareClass, NavDaily.fund_share_class_id == FundShareClass.id)
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("quote").label("category"),
                func.max(MarketQuote.collected_at).label("collected_at"),
            )
            .join(FundListing, MarketQuote.fund_listing_id == FundListing.id)
            .join(FundShareClass, FundListing.fund_share_class_id == FundShareClass.id)
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("scale").label("category"),
                func.max(FundScale.collected_at).label("collected_at"),
            )
            .outerjoin(FundShareClass, FundScale.fund_share_class_id == FundShareClass.id)
            .where(
                or_(
                    FundScale.fund_product_id.in_(product_ids),
                    FundShareClass.fund_product_id.in_(product_ids),
                )
            ),
            select(
                literal("fee").label("category"),
                func.max(FeeHistory.collected_at).label("collected_at"),
            )
            .join(FundShareClass, FeeHistory.fund_share_class_id == FundShareClass.id)
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("metric").label("category"),
                func.max(CalculatedMetric.collected_at).label("collected_at"),
            )
            .join(FundShareClass, CalculatedMetric.fund_share_class_id == FundShareClass.id)
            .where(FundShareClass.fund_product_id.in_(product_ids)),
            select(
                literal("subscription").label("category"),
                func.max(SalesLimitHistory.collected_at).label("collected_at"),
            )
            .join(
                FundShareClass,
                SalesLimitHistory.fund_share_class_id == FundShareClass.id,
            )
            .where(FundShareClass.fund_product_id.in_(product_ids)),
        )
        freshness_rows = union_all(*statements).subquery()
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    freshness_rows.c.category,
                    func.max(freshness_rows.c.collected_at),
                ).group_by(freshness_rows.c.category)
            )
            return DataFreshness(
                **{
                    category: collected_at
                    for category, collected_at in rows
                    if collected_at is not None
                }
            )

    def get_last_synced_at(
        self,
        index_id: str,
        venue: str | None = None,
        exchanges: tuple[str, ...] = (),
    ) -> datetime | None:
        return self.get_data_freshness(index_id, venue, exchanges).latest_at

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
            tags_by_share = self._load_user_tags(
                session, [row["share_id"] for row in row_dicts]
            )
            return [
                self._fund_row(
                    row,
                    fees_by_share.get(row["share_id"], {}),
                    metrics_by_share.get(row["share_id"], {}),
                    tags_by_share.get(row["share_id"], []),
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
            tags_by_share = self._load_user_tags(
                session, [row["share_id"] for row in row_dicts]
            )
            funds_by_code = {
                row["ticker"] or row["code"]: self._fund_row(
                    row,
                    fees_by_share.get(row["share_id"], {}),
                    metrics_by_share.get(row["share_id"], {}),
                    tags_by_share.get(row["share_id"], []),
                )
                for row in row_dicts
            }
            return [funds_by_code[code] for code in codes if code in funds_by_code]

    def set_fund_tags(
        self, code: str, tags: list[FundTagType]
    ) -> list[FundTagType] | None:
        normalized = sorted(set(tags), key=FUND_TAG_ORDER.__getitem__)
        with self._session_factory() as session:
            share_id = session.scalar(
                select(FundShareClass.id)
                .outerjoin(
                    FundListing,
                    FundListing.fund_share_class_id == FundShareClass.id,
                )
                .where(
                    or_(FundShareClass.code == code, FundListing.ticker == code),
                    FundShareClass.status == "active",
                )
            )
            if share_id is None:
                return None

            session.execute(
                delete(UserFundTag).where(
                    UserFundTag.user_id == SINGLE_USER_ID,
                    UserFundTag.fund_share_class_id == share_id,
                )
            )
            session.add_all(
                UserFundTag(
                    user_id=SINGLE_USER_ID,
                    fund_share_class_id=share_id,
                    tag_type=tag.value,
                )
                for tag in normalized
            )
            session.commit()
            return normalized

    def list_notes(
        self,
        query: str | None = None,
        category: str | None = None,
        year: int | None = None,
    ) -> list[InvestmentNoteItem]:
        with self._session_factory() as session:
            statement = select(InvestmentNote).where(
                InvestmentNote.user_id == SINGLE_USER_ID
            )
            if category is not None:
                statement = statement.where(InvestmentNote.category == category)
            if year is not None:
                statement = statement.where(
                    func.extract("year", InvestmentNote.note_date) == year
                )
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                statement = statement.where(
                    or_(
                        InvestmentNote.title.ilike(pattern),
                        InvestmentNote.source_name.ilike(pattern),
                        InvestmentNote.source_excerpt.ilike(pattern),
                        InvestmentNote.own_summary.ilike(pattern),
                        InvestmentNote.content_markdown.ilike(pattern),
                    )
                )
            notes = session.scalars(
                statement.order_by(
                    InvestmentNote.note_date.desc(), InvestmentNote.id.desc()
                )
            ).all()
            return [_note_item(note) for note in notes]

    def create_note(self, payload: InvestmentNoteCreate) -> InvestmentNoteItem:
        with self._session_factory() as session:
            note = InvestmentNote(
                user_id=SINGLE_USER_ID,
                **_normalized_note_values(payload),
            )
            session.add(note)
            session.commit()
            session.refresh(note)
            return _note_item(note)

    def update_note(
        self, note_id: int, payload: InvestmentNoteUpdate
    ) -> InvestmentNoteItem | None:
        with self._session_factory() as session:
            note = session.scalar(
                select(InvestmentNote).where(
                    InvestmentNote.id == note_id,
                    InvestmentNote.user_id == SINGLE_USER_ID,
                )
            )
            if note is None:
                return None
            for field, value in _normalized_note_values(payload).items():
                setattr(note, field, value)
            note.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(note)
            return _note_item(note)

    def delete_note(self, note_id: int) -> bool:
        with self._session_factory() as session:
            note = session.scalar(
                select(InvestmentNote).where(
                    InvestmentNote.id == note_id,
                    InvestmentNote.user_id == SINGLE_USER_ID,
                )
            )
            if note is None:
                return False
            session.delete(note)
            session.commit()
            return True

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
        same_day_quote = aliased(MarketQuote)
        latest_scale = aliased(FundScale)
        latest_subscription = aliased(SalesLimitHistory)
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
        same_day_quote_id = (
            select(MarketQuote.id)
            .where(
                MarketQuote.fund_listing_id == FundListing.id,
                MarketQuote.trade_date == latest_nav.nav_date,
            )
            .order_by(MarketQuote.id.desc())
            .limit(1)
            .correlate(FundListing, latest_nav)
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
        latest_subscription_id = (
            select(SalesLimitHistory.id)
            .where(
                SalesLimitHistory.fund_share_class_id == FundShareClass.id,
                SalesLimitHistory.business_type == "申购",
                or_(
                    SalesLimitHistory.effective_from.is_(None),
                    SalesLimitHistory.effective_from <= func.now(),
                ),
                or_(
                    SalesLimitHistory.effective_to.is_(None),
                    SalesLimitHistory.effective_to > func.now(),
                ),
            )
            .order_by(
                SalesLimitHistory.effective_from.desc().nullslast(),
                SalesLimitHistory.id.desc(),
            )
            .limit(1)
            .correlate(FundShareClass)
        )

        return (
            select(
                FundShareClass.id.label("share_id"),
                FundShareClass.code,
                FundShareClass.display_name,
                FundShareClass.share_class,
                FundShareClass.currency,
                latest_subscription.limit_status.label("subscription_status"),
                latest_subscription.limit_amount.label("subscription_limit_amount"),
                latest_subscription.currency.label("subscription_limit_currency"),
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
                same_day_quote.close_price.label("deviation_close_price"),
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
            .outerjoin(
                same_day_quote,
                same_day_quote.id == same_day_quote_id.scalar_subquery(),
            )
            .outerjoin(latest_scale, latest_scale.id == latest_scale_id.scalar_subquery())
            .outerjoin(
                latest_subscription,
                latest_subscription.id == latest_subscription_id.scalar_subquery(),
            )
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

    @staticmethod
    def _load_user_tags(
        session: Session, share_ids: list[int]
    ) -> dict[int, list[FundTagType]]:
        if not share_ids:
            return {}
        tags_by_share: dict[int, list[FundTagType]] = {}
        rows = session.execute(
            select(UserFundTag.fund_share_class_id, UserFundTag.tag_type).where(
                UserFundTag.user_id == SINGLE_USER_ID,
                UserFundTag.fund_share_class_id.in_(share_ids),
            )
        )
        for share_id, tag_type in rows:
            try:
                tags_by_share.setdefault(share_id, []).append(FundTagType(tag_type))
            except ValueError:
                continue
        for tags in tags_by_share.values():
            tags.sort(key=FUND_TAG_ORDER.__getitem__)
        return tags_by_share

    def _fund_row(
        self,
        row: dict[str, Any],
        fees: dict[str, float],
        latest_metrics: dict[str, CalculatedMetric],
        tags: list[FundTagType],
    ) -> FundComparisonRow:

        management = fees.get("management")
        custody = fees.get("custody")
        sales_service = fees.get("sales_service")
        comprehensive_operating = fees.get("comprehensive_operating")
        expense_rate = calculate_operating_rate(
            management,
            custody,
            sales_service,
            comprehensive_operating,
        )
        nav = float(row["nav"]) if row["nav"] is not None else None
        close = float(row["close_price"]) if row["close_price"] is not None else None
        investment_scopes = row["investment_scopes"] or []
        is_qdii = any("QDII" in str(scope).upper() for scope in investment_scopes)
        deviation_close = close if is_qdii else (
            float(row["deviation_close_price"])
            if row["deviation_close_price"] is not None
            else None
        )
        deviation_close_date = row["close_date"] if is_qdii else row["nav_date"]
        estimated_deviation = calculate_estimated_deviation(
            deviation_close,
            deviation_close_date,
            nav,
            row["nav_date"],
            allow_lagged_nav=is_qdii,
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
            subscription_status=row["subscription_status"],
            subscription_limit_amount=(
                float(row["subscription_limit_amount"])
                if row["subscription_limit_amount"] is not None
                else None
            ),
            subscription_limit_currency=row["subscription_limit_currency"],
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
            tags=tags,
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
