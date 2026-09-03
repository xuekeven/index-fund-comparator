"""add knowledge article order

Revision ID: d9e0f1a2b345
Revises: c8d9e0f1a234
Create Date: 2026-09-03 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b345"
down_revision: Union[str, None] = "c8d9e0f1a234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_article",
        sa.Column("category_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "knowledge_article",
        sa.Column("article_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                dense_rank() OVER (PARTITION BY user_id ORDER BY category) - 1
                    AS category_order,
                row_number() OVER (
                    PARTITION BY user_id, category ORDER BY title, id
                ) - 1 AS article_order
            FROM knowledge_article
        )
        UPDATE knowledge_article AS article
        SET category_order = ranked.category_order,
            article_order = ranked.article_order
        FROM ranked
        WHERE article.id = ranked.id
        """
    )
    op.create_index(
        "ix_knowledge_article_user_order",
        "knowledge_article",
        ["user_id", "category_order", "article_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_article_user_order", table_name="knowledge_article")
    op.drop_column("knowledge_article", "article_order")
    op.drop_column("knowledge_article", "category_order")
