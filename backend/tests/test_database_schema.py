from app.database_models import Base


CORE_TABLES = {
    "source_document",
    "index_family",
    "index_definition",
    "fund_product",
    "fund_share_class",
    "fund_listing",
    "fee_history",
    "nav_daily",
    "market_quote",
    "benchmark_daily",
    "fund_scale",
    "sales_limit_history",
    "calculated_metric",
}


def test_all_core_tables_are_declared() -> None:
    assert set(Base.metadata.tables) == CORE_TABLES


def test_fund_entities_are_separate_and_linked() -> None:
    share_table = Base.metadata.tables["fund_share_class"]
    listing_table = Base.metadata.tables["fund_listing"]

    share_foreign_keys = {key.target_fullname for key in share_table.foreign_keys}
    listing_foreign_keys = {key.target_fullname for key in listing_table.foreign_keys}

    assert "fund_product.id" in share_foreign_keys
    assert "fund_share_class.id" in listing_foreign_keys


def test_product_scope_excludes_lof() -> None:
    product_table = Base.metadata.tables["fund_product"]
    structure_constraint = next(
        constraint
        for constraint in product_table.constraints
        if constraint.name == "ck_fund_product_structure"
    )

    assert "LOF" not in str(structure_constraint.sqltext)
