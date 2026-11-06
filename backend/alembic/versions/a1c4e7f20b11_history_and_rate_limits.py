"""client history and shared rate limits"""

import sqlalchemy as sa
from alembic import op

revision = "a1c4e7f20b11"
down_revision = "69d05a5a0da1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_id", sa.Uuid(), nullable=True),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_key", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_client_history_client_created",
        "client_history",
        ["client_id", sa.text("created_at DESC")],
    )
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("tokens", sa.Float(53), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_limits")
    op.drop_index("ix_client_history_client_created", table_name="client_history")
    op.drop_table("client_history")
