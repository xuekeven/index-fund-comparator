from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProvenanceMixin:
    source_document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("source_document.id", ondelete="SET NULL")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    quality_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'unavailable'")
    )


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_document"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    raw_storage_path: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint("url", "retrieved_at", name="uq_source_document_url_retrieved_at"),
        Index("ix_source_document_published_at", "published_at"),
    )


class IndexFamily(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "index_family"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))

    __table_args__ = (
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_index_family_quality_status",
        ),
    )


class IndexDefinition(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "index_definition"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("index_family.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(32), nullable=False)
    index_code: Mapped[str | None] = mapped_column(String(64))
    benchmark_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fx_adjustment: Mapped[str | None] = mapped_column(String(200))
    exact_benchmark: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))

    __table_args__ = (
        CheckConstraint(
            "benchmark_type IN ('价格指数', '净收益指数', '全收益指数', '自定义业绩基准')",
            name="ck_index_definition_benchmark_type",
        ),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_index_definition_quality_status",
        ),
        Index("ix_index_definition_provider_code", "provider", "index_code"),
        Index("ix_index_definition_family", "family_id"),
    )


class FundProduct(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "fund_product"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    canonical_code: Mapped[str] = mapped_column(String(120), nullable=False)
    registration_code: Mapped[str | None] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fund_company: Mapped[str] = mapped_column(String(200), nullable=False)
    product_structure: Mapped[str] = mapped_column(String(40), nullable=False)
    trading_venue: Mapped[str] = mapped_column(String(20), nullable=False)
    investment_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    tracking_method: Mapped[str] = mapped_column(String(24), nullable=False)
    exact_benchmark_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("index_definition.id", ondelete="RESTRICT")
    )
    benchmark_description: Mapped[str] = mapped_column(Text, nullable=False)
    feeder_target_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fund_product.id", name="fk_fund_product_feeder_target", ondelete="SET NULL"),
    )
    inception_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))

    __table_args__ = (
        CheckConstraint(
            "product_structure IN ('ETF', '普通开放式指数基金', 'ETF联接基金')",
            name="ck_fund_product_structure",
        ),
        CheckConstraint(
            "trading_venue IN ('仅场内', '仅场外')",
            name="ck_fund_product_trading_venue",
        ),
        CheckConstraint(
            "tracking_method IN ('被动指数', '指数增强')",
            name="ck_fund_product_tracking_method",
        ),
        CheckConstraint(
            "((product_structure = 'ETF' AND trading_venue = '仅场内') OR "
            "(product_structure <> 'ETF' AND trading_venue = '仅场外'))",
            name="ck_fund_product_structure_venue",
        ),
        Index("ix_fund_product_benchmark", "exact_benchmark_id"),
        Index("ix_fund_product_structure_method", "product_structure", "tracking_method"),
        UniqueConstraint("canonical_code", name="uq_fund_product_canonical_code"),
    )


class FundShareClass(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "fund_share_class"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_product.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    share_class: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'人民币'"))
    currency_form: Mapped[str | None] = mapped_column(String(32))
    inception_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'active'"))

    __table_args__ = (
        UniqueConstraint(
            "fund_product_id", "share_class", "currency", "currency_form",
            name="uq_fund_share_class_identity",
        ),
        Index("ix_fund_share_class_product", "fund_product_id"),
    )


class FundListing(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "fund_listing"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_share_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE"), nullable=False
    )
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    listing_name: Mapped[str | None] = mapped_column(String(100))
    listing_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'listed'"))

    __table_args__ = (
        CheckConstraint("exchange IN ('上交所', '深交所')", name="ck_fund_listing_exchange"),
        UniqueConstraint("exchange", "ticker", name="uq_fund_listing_exchange_ticker"),
        UniqueConstraint("fund_share_class_id", name="uq_fund_listing_share_class"),
    )


class FeeHistory(Base, ProvenanceMixin):
    __tablename__ = "fee_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_share_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE"), nullable=False
    )
    fee_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 8), nullable=False)
    rate_unit: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'percent'"))
    tier_description: Mapped[str | None] = mapped_column(Text)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "fee_type IN ('management', 'custody', 'sales_service', 'subscription', 'redemption', 'other')",
            name="ck_fee_history_type",
        ),
        CheckConstraint("rate >= 0", name="ck_fee_history_rate_nonnegative"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_fee_history_quality_status",
        ),
        Index("ix_fee_history_share_type_effective", "fund_share_class_id", "fee_type", "effective_from"),
    )


class NavDaily(Base, ProvenanceMixin):
    __tablename__ = "nav_daily"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_share_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE"), nullable=False
    )
    nav_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit_nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    accumulated_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    __table_args__ = (
        CheckConstraint("unit_nav > 0", name="ck_nav_daily_unit_nav_positive"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_nav_daily_quality_status",
        ),
        UniqueConstraint("fund_share_class_id", "nav_date", name="uq_nav_daily_share_date"),
        Index("ix_nav_daily_date", "nav_date"),
    )


class MarketQuote(Base, ProvenanceMixin):
    __tablename__ = "market_quote"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_listing.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    turnover_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    iopv: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    __table_args__ = (
        CheckConstraint("close_price >= 0", name="ck_market_quote_close_nonnegative"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_market_quote_quality_status",
        ),
        UniqueConstraint("fund_listing_id", "trade_date", name="uq_market_quote_listing_date"),
        Index("ix_market_quote_trade_date", "trade_date"),
    )


class BenchmarkDaily(Base, ProvenanceMixin):
    __tablename__ = "benchmark_daily"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    index_definition_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("index_definition.id", ondelete="CASCADE"), nullable=False
    )
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    __table_args__ = (
        CheckConstraint("value > 0", name="ck_benchmark_daily_value_positive"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_benchmark_daily_quality_status",
        ),
        UniqueConstraint("index_definition_id", "value_date", name="uq_benchmark_daily_index_date"),
        Index("ix_benchmark_daily_value_date", "value_date"),
    )


class FundScale(Base, ProvenanceMixin):
    __tablename__ = "fund_scale"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fund_product.id", ondelete="CASCADE")
    )
    fund_share_class_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE")
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'人民币'"))
    amount_cny: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))

    __table_args__ = (
        CheckConstraint(
            "((fund_product_id IS NOT NULL)::int + (fund_share_class_id IS NOT NULL)::int) = 1",
            name="ck_fund_scale_single_owner",
        ),
        CheckConstraint("amount >= 0", name="ck_fund_scale_amount_nonnegative"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_fund_scale_quality_status",
        ),
        Index("ix_fund_scale_product_date", "fund_product_id", "report_date"),
        Index("ix_fund_scale_share_date", "fund_share_class_id", "report_date"),
    )


class SalesLimitHistory(Base, ProvenanceMixin):
    __tablename__ = "sales_limit_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_share_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(120), nullable=False)
    investor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    business_type: Mapped[str] = mapped_column(String(64), nullable=False)
    limit_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    currency: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'人民币'"))
    limit_status: Mapped[str] = mapped_column(String(24), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("limit_amount IS NULL OR limit_amount >= 0", name="ck_sales_limit_amount_nonnegative"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_sales_limit_quality_status",
        ),
        Index(
            "ix_sales_limit_share_effective", "fund_share_class_id", "effective_from", "effective_to"
        ),
    )


class CalculatedMetric(Base, ProvenanceMixin):
    __tablename__ = "calculated_metric"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fund_share_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fund_share_class.id", ondelete="CASCADE"), nullable=False
    )
    index_definition_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("index_definition.id", ondelete="SET NULL")
    )
    metric_code: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    value_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_inputs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="ck_calculated_metric_period"),
        CheckConstraint(
            "quality_status IN ('verified', 'delayed', 'sample', 'unavailable', 'estimated')",
            name="ck_calculated_metric_quality_status",
        ),
        UniqueConstraint(
            "fund_share_class_id", "metric_code", "period_start", "period_end", "calculation_version",
            name="uq_calculated_metric_identity",
        ),
        Index("ix_calculated_metric_share_code_end", "fund_share_class_id", "metric_code", "period_end"),
    )
