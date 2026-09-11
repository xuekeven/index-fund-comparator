"""remove knowledge summary and reviewed at

Revision ID: a3b4c5d6e789
Revises: f2a3b4c5d678
Create Date: 2026-09-11 12:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e789"
down_revision: Union[str, None] = "f2a3b4c5d678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("knowledge_article", "reviewed_at")
    op.drop_column("knowledge_article", "summary")


def downgrade() -> None:
    op.add_column(
        "knowledge_article",
        sa.Column("summary", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.add_column(
        "knowledge_article",
        sa.Column("reviewed_at", sa.Date(), nullable=True),
    )
