"""add recurring fund tag

Revision ID: e31b7d5c0a42
Revises: c9f3d7a2e810
Create Date: 2026-08-29 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e31b7d5c0a42"
down_revision: Union[str, None] = "c9f3d7a2e810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_user_fund_tag_type",
        "user_fund_tag",
        type_="check",
    )
    op.create_check_constraint(
        "ck_user_fund_tag_type",
        "user_fund_tag",
        "tag_type IN ('favorite', 'holding', 'recurring')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_fund_tag WHERE tag_type = 'recurring'")
    op.drop_constraint(
        "ck_user_fund_tag_type",
        "user_fund_tag",
        type_="check",
    )
    op.create_check_constraint(
        "ck_user_fund_tag_type",
        "user_fund_tag",
        "tag_type IN ('favorite', 'holding')",
    )
