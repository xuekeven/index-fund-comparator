"""add optional amount to user fund tags

Revision ID: f2a3b4c5d678
Revises: e0f1a2b3c456
Create Date: 2026-09-09 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d678"
down_revision: Union[str, None] = "e0f1a2b3c456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_fund_tag",
        sa.Column("amount", sa.Numeric(precision=24, scale=6), nullable=True),
    )
    op.create_check_constraint(
        "ck_user_fund_tag_amount",
        "user_fund_tag",
        "amount IS NULL OR amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_fund_tag_amount",
        "user_fund_tag",
        type_="check",
    )
    op.drop_column("user_fund_tag", "amount")
