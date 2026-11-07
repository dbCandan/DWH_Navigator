"""Split the term_list running uniqueness from per-tenant to per-owner.

Drops uq_term_list_one_running_per_tenant and creates two partial unique indexes so that an
account's running list and a visitor's running list are each unique per tenant, but different
owners' lists may run at the same time.

Spec: data-dictionary/PRDs/005-list-search (Decision 3, Requirement 4; Version 1.3.0).

Revision ID: 202611040001
Revises: 202610140001
Create Date: 2026-11-04 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202611040001"
down_revision: str | None = "202610140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COMMENT = (
    "A term list of the data-dictionary context (list-search capability): an uploaded "
    "one-column Excel list whose terms go one by one through the question analysis. Owned by "
    "the uploading account or visitor, the newest five per owner are kept, an older one is "
    "deleted physically with its terms (is_deleted stays false). At most one running list per "
    "owner; different owners' lists may run at the same time. The uploaded file itself is "
    "never stored."
)
_OLD_COMMENT = (
    "A term list of the data-dictionary context (list-search capability): an uploaded "
    "one-column Excel list whose terms go one by one through the question analysis. Owned by "
    "the uploading account or visitor, the newest five per owner are kept, an older one is "
    "deleted physically with its terms (is_deleted stays false). At most one running list per "
    "tenant. The uploaded file itself is never stored."
)


def upgrade() -> None:
    op.drop_index(
        "uq_term_list_one_running_per_tenant",
        table_name="term_list",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index(
        "uq_term_list_one_running_per_owner_user",
        "term_list",
        ["tenant_id", "owner_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running' AND owner_id IS NOT NULL"),
    )
    op.create_index(
        "uq_term_list_one_running_per_owner_visitor",
        "term_list",
        ["tenant_id", "owner_visitor_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running' AND owner_visitor_id IS NOT NULL"),
    )
    op.execute("COMMENT ON TABLE term_list IS '" + _NEW_COMMENT.replace("'", "''") + "'")


def downgrade() -> None:
    op.execute("COMMENT ON TABLE term_list IS '" + _OLD_COMMENT.replace("'", "''") + "'")
    op.drop_index(
        "uq_term_list_one_running_per_owner_visitor",
        table_name="term_list",
        postgresql_where=sa.text("status = 'running' AND owner_visitor_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_term_list_one_running_per_owner_user",
        table_name="term_list",
        postgresql_where=sa.text("status = 'running' AND owner_id IS NOT NULL"),
    )
    op.create_index(
        "uq_term_list_one_running_per_tenant",
        "term_list",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
