"""Add audit log user foreign key

Revision ID: d24b05f4a104
Revises: 6e3503a395b6
Create Date: 2026-10-08 18:20:19.204814

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d24b05f4a104"
down_revision: Union[str, Sequence[str], None] = "6e3503a395b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        "fk_audit_logs_user_id_users",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_audit_logs_user_id_users",
        "audit_logs",
        type_="foreignkey",
    )