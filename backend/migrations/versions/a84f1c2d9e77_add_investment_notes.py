"""add investment notes

Revision ID: a84f1c2d9e77
Revises: e31b7d5c0a42
Create Date: 2026-08-30 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a84f1c2d9e77"
down_revision: Union[str, None] = "e31b7d5c0a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_note",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("note_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("own_summary", sa.Text(), nullable=True),
        sa.Column(
            "content_markdown",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            sa.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "index_ids",
            sa.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "fund_codes",
            sa.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
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
            "category IN ('长期', '实时')",
            name="ck_investment_note_category",
        ),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('加仓', '减仓', '清仓', '持有', '观察')",
            name="ck_investment_note_action",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investment_note_user_date",
        "investment_note",
        ["user_id", "note_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_investment_note_user_date", table_name="investment_note")
    op.drop_table("investment_note")
