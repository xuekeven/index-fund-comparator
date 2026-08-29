"""add single-user fund tags

Revision ID: c9f3d7a2e810
Revises: b442c1f4367d
Create Date: 2026-08-28 11:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f3d7a2e810"
down_revision: Union[str, None] = "b442c1f4367d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_fund_tag",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("fund_share_class_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_type", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tag_type IN ('favorite', 'holding')",
            name="ck_user_fund_tag_type",
        ),
        sa.ForeignKeyConstraint(
            ["fund_share_class_id"],
            ["fund_share_class.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "fund_share_class_id",
            "tag_type",
            name="uq_user_fund_tag_identity",
        ),
    )
    op.create_index(
        "ix_user_fund_tag_share",
        "user_fund_tag",
        ["fund_share_class_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_fund_tag_user",
        "user_fund_tag",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_fund_tag_user", table_name="user_fund_tag")
    op.drop_index("ix_user_fund_tag_share", table_name="user_fund_tag")
    op.drop_table("user_fund_tag")
