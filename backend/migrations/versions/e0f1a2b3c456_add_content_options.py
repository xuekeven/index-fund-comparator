"""add content options

Revision ID: e0f1a2b3c456
Revises: d9e0f1a2b345
Create Date: 2026-09-07 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0f1a2b3c456"
down_revision: Union[str, None] = "d9e0f1a2b345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_option",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("option_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "option_type IN ('investment_note_source', 'knowledge_category')",
            name="ck_content_option_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "option_type", "value", name="uq_content_option_identity"
        ),
    )
    op.create_index(
        "ix_content_option_user_type_order",
        "content_option",
        ["user_id", "option_type", "sort_order"],
        unique=False,
    )
    options = [
        ("investment_note_source", "自我总结"),
        ("investment_note_source", "教主-群聊"),
        ("investment_note_source", "教主-微博"),
        ("investment_note_source", "猫笔刀-日报"),
        ("investment_note_source", "仓鼠投资-微博"),
        ("knowledge_category", "资产配置"),
        ("knowledge_category", "利率"),
        ("knowledge_category", "债券"),
        ("knowledge_category", "黄金"),
        ("knowledge_category", "红利策略"),
        ("knowledge_category", "交易工具"),
    ]
    option_table = sa.table(
        "content_option",
        sa.column("user_id", sa.String()),
        sa.column("option_type", sa.String()),
        sa.column("value", sa.String()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        option_table,
        [
            {"user_id": "default", "option_type": kind, "value": value, "sort_order": order}
            for order, (kind, value) in enumerate(options)
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_content_option_user_type_order", table_name="content_option")
    op.drop_table("content_option")
