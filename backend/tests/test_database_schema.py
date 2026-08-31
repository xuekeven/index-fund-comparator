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
    "user_fund_tag",
    "investment_note",
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


def test_single_user_tags_are_bound_to_fund_shares() -> None:
    tag_table = Base.metadata.tables["user_fund_tag"]
    foreign_keys = {key.target_fullname for key in tag_table.foreign_keys}
    tag_constraint = next(
        constraint
        for constraint in tag_table.constraints
        if constraint.name == "ck_user_fund_tag_type"
    )

    assert "fund_share_class.id" in foreign_keys
    assert "favorite" in str(tag_constraint.sqltext)
    assert "holding" in str(tag_constraint.sqltext)
    assert "recurring" in str(tag_constraint.sqltext)


def test_fee_history_accepts_comprehensive_operating_rate() -> None:
    fee_table = Base.metadata.tables["fee_history"]
    fee_constraint = next(
        constraint
        for constraint in fee_table.constraints
        if constraint.name == "ck_fee_history_type"
    )

    assert "comprehensive_operating" in str(fee_constraint.sqltext)



def test_investment_notes_are_single_user_and_structured() -> None:
    note_table = Base.metadata.tables["investment_note"]
    category_constraint = next(
        constraint
        for constraint in note_table.constraints
        if constraint.name == "ck_investment_note_category"
    )
    action_constraint = next(
        constraint
        for constraint in note_table.constraints
        if constraint.name == "ck_investment_note_action"
    )

    assert "user_id" in note_table.columns
    assert "长期" in str(category_constraint.sqltext)
    assert "实时" in str(category_constraint.sqltext)
    assert "加仓" in str(action_constraint.sqltext)
    assert "index_ids" in note_table.columns
    assert "fund_codes" in note_table.columns
