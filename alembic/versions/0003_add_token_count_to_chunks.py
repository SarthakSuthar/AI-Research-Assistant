"""add token_count to chunks

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default="0" means:
    # 1. All existing rows receive token_count = 0 immediately (no NULL)
    # 2. New INSERTs that omit token_count also default to 0
    # This makes the migration non-destructive and reversible.
    op.add_column(
        "chunks",
        sa.Column(
            "token_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "token_count")
