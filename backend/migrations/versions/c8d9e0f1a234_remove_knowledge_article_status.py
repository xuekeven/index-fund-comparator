"""remove knowledge article status

Revision ID: c8d9e0f1a234
Revises: b7c8d9e0f123
Create Date: 2026-09-02 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a234"
down_revision: Union[str, None] = "b7c8d9e0f123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_knowledge_article_user_status", table_name="knowledge_article")
    op.drop_constraint(
        "ck_knowledge_article_status", "knowledge_article", type_="check"
    )
    op.drop_column("knowledge_article", "status")


def downgrade() -> None:
    op.add_column(
        "knowledge_article",
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'草稿'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_knowledge_article_status",
        "knowledge_article",
        "status IN ('草稿', '已发布', '待复核')",
    )
    op.create_index(
        "ix_knowledge_article_user_status",
        "knowledge_article",
        ["user_id", "status"],
        unique=False,
    )
