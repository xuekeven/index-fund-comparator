import os
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database_models import (
    Base,
    CalculatedMetric,
    FeeHistory,
    FundProduct,
    FundScale,
    FundShareClass,
    IndexDefinition,
    IndexFamily,
    NavDaily,
    SalesLimitHistory,
)
from app.models import FundTagType, InvestmentNoteCreate
from app.repository import PostgresFundRepository


TEST_DATABASE_URL = os.getenv("IFC_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="IFC_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture(scope="module")
def repository():
    assert TEST_DATABASE_URL is not None
    database_name = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?", 1)[0]
    if database_name != "index_fund_comparator_test":
        raise RuntimeError(
            "PostgreSQL integration tests require the dedicated "
            "index_fund_comparator_test database"
        )

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    collected_times = {
        name: datetime(2026, 8, 31, hour, tzinfo=UTC)
        for name, hour in {
            "master": 1,
            "nav": 2,
            "fee": 3,
            "scale": 4,
            "metric": 5,
            "subscription": 6,
        }.items()
    }

    with factory() as session:
        family = IndexFamily(
            id="sp-500",
            name="标普500指数",
            short_name="标普500",
            region="美国",
            currency="美元",
            quality_status="verified",
            collected_at=collected_times["master"],
        )
        definition = IndexDefinition(
            id="sp-500-price",
            family_id=family.id,
            name="标普500价格指数",
            short_name="标普500",
            provider="S&P DJI",
            region="美国",
            currency="美元",
            benchmark_type="价格指数",
            exact_benchmark="标普500指数收益率",
            quality_status="verified",
            collected_at=collected_times["master"],
        )
        product = FundProduct(
            canonical_code="test:000001",
            name="测试标普500指数基金",
            fund_company="测试基金公司",
            product_structure="普通开放式指数基金",
            trading_venue="仅场外",
            investment_scopes=["QDII"],
            tracking_method="被动指数",
            exact_benchmark_id=definition.id,
            benchmark_description=definition.exact_benchmark,
            quality_status="verified",
            collected_at=collected_times["master"],
        )
        session.add(family)
        session.flush()
        session.add(definition)
        session.flush()
        session.add(product)
        session.flush()
        share = FundShareClass(
            fund_product_id=product.id,
            code="000001",
            display_name="测试标普500指数人民币C",
            share_class="C",
            currency="人民币",
            quality_status="verified",
            collected_at=collected_times["master"],
        )
        session.add(share)
        session.flush()
        session.add_all(
            [
                FeeHistory(
                    fund_share_class_id=share.id,
                    fee_type=fee_type,
                    rate=rate,
                    rate_unit="percent",
                    effective_from=collected_times["fee"],
                    collected_at=collected_times["fee"],
                    quality_status="verified",
                )
                for fee_type, rate in {
                    "management": Decimal("0.60"),
                    "custody": Decimal("0.20"),
                    "sales_service": Decimal("0.35"),
                    "comprehensive_operating": Decimal("1.18"),
                }.items()
            ]
        )
        session.add(
            NavDaily(
                fund_share_class_id=share.id,
                nav_date=date(2026, 8, 29),
                unit_nav=Decimal("1.2345"),
                effective_from=collected_times["nav"],
                collected_at=collected_times["nav"],
                quality_status="verified",
            )
        )
        session.add(
            FundScale(
                fund_share_class_id=share.id,
                report_date=date(2026, 6, 30),
                amount=Decimal("100000000"),
                amount_cny=Decimal("100000000"),
                effective_from=collected_times["scale"],
                collected_at=collected_times["scale"],
                quality_status="verified",
            )
        )
        session.add(
            CalculatedMetric(
                fund_share_class_id=share.id,
                index_definition_id=definition.id,
                metric_code="return_1m",
                period_start=date(2026, 7, 29),
                period_end=date(2026, 8, 29),
                value=Decimal("2.5"),
                value_unit="percent",
                calculation_version="test-v1",
                effective_from=collected_times["metric"],
                collected_at=collected_times["metric"],
                quality_status="verified",
            )
        )
        session.add(
            SalesLimitHistory(
                fund_share_class_id=share.id,
                channel="基金公司直销",
                investor_type="个人",
                business_type="申购",
                limit_amount=Decimal("100"),
                currency="人民币",
                limit_status="limited",
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                collected_at=collected_times["subscription"],
                quality_status="verified",
            )
        )
        session.commit()

    yield PostgresFundRepository(factory)

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_postgres_repository_loads_production_fund_query(repository) -> None:
    funds = repository.list_funds("sp-500")

    assert len(funds) == 1
    fund = funds[0]
    assert fund.code == "000001"
    assert fund.management_fee == 0.6
    assert fund.custody_fee == 0.2
    assert fund.sales_service_fee == 0.35
    assert fund.expense_rate == pytest.approx(1.18)
    assert fund.returns[0].period == "1月"
    assert fund.subscription_status == "limited"


def test_postgres_repository_returns_category_freshness(repository) -> None:
    freshness = repository.get_data_freshness("sp-500", venue="场外")

    assert freshness.master == datetime(2026, 8, 31, 1, tzinfo=UTC)
    assert freshness.nav == datetime(2026, 8, 31, 2, tzinfo=UTC)
    assert freshness.quote is None
    assert freshness.fee == datetime(2026, 8, 31, 3, tzinfo=UTC)
    assert freshness.scale == datetime(2026, 8, 31, 4, tzinfo=UTC)
    assert freshness.metric == datetime(2026, 8, 31, 5, tzinfo=UTC)
    assert freshness.subscription == datetime(2026, 8, 31, 6, tzinfo=UTC)
    assert repository.get_last_synced_at("sp-500", venue="场外") == freshness.latest_at


def test_postgres_repository_persists_tags_and_notes(repository) -> None:
    tags = repository.set_fund_tags(
        "000001",
        [FundTagType.FAVORITE, FundTagType.RECURRING],
    )
    assert [tag.value for tag in tags or []] == ["favorite", "recurring"]
    assert [tag.value for tag in repository.get_fund("000001").tags] == [
        "favorite",
        "recurring",
    ]

    note = repository.create_note(
        InvestmentNoteCreate(
            note_date=date(2026, 8, 31),
            title="PostgreSQL 集成测试",
            category="实时",
        )
    )
    assert repository.list_notes(query="集成测试")[0].id == note.id
    assert repository.delete_note(note.id)
