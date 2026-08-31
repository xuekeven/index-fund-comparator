"""add comprehensive operating fee type

Revision ID: d6e7f8a9b012
Revises: a84f1c2d9e77
Create Date: 2026-08-31 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d6e7f8a9b012"
down_revision: Union[str, None] = "a84f1c2d9e77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_fee_history_type", "fee_history", type_="check")
    op.create_check_constraint(
        "ck_fee_history_type",
        "fee_history",
        "fee_type IN ('management', 'custody', 'sales_service', "
        "'comprehensive_operating', 'subscription', 'redemption', 'other')",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM fee_history WHERE fee_type = 'comprehensive_operating'"
    )
    op.drop_constraint("ck_fee_history_type", "fee_history", type_="check")
    op.create_check_constraint(
        "ck_fee_history_type",
        "fee_history",
        "fee_type IN ('management', 'custody', 'sales_service', "
        "'subscription', 'redemption', 'other')",
    )
