"""Add the visitor (visitor) and let analyses, votes and lists belong to an account or a visitor.

Expand-only: a new table; analysis_record, answer_vote and term_list gain a nullable visitor
reference, the visitor's address and host name, and a check that exactly one of the account and
the visitor column is set. The account columns become nullable; existing rows keep their account.
Downgrade deletes the rows a visitor owns (analyses, votes, lists with their terms) before the
account columns become required again, then drops the visitor table.

Spec: application-foundation/PRDs/003-anonymous-visitor (Veri ve geçiş).

Revision ID: 202610140001
Revises: 202610090003
Create Date: 2026-10-14 20:42:44.268402
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610140001"
down_revision: str | None = "202610090003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visitor",
        sa.Column(
            "visitor_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "public_id",
            sa.String(length=36),
            nullable=False,
            comment="The visitor's own random id (UUID), unrelated to the device id it sends.",
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant (the single platform tenant); references tenant.tenant_id.",
        ),
        sa.Column(
            "device_key",
            sa.String(length=64),
            nullable=False,
            comment="Lower-case hex SHA-256 of the device id the browser sends in X-Device-Id; the id itself is never stored.",
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="The visitor's first request (UTC).",
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="The visitor's latest request (UTC).",
        ),
        sa.Column(
            "last_address",
            sa.String(length=45),
            nullable=False,
            comment="The client IP address of the latest request, resolved through the trusted ingress networks only (personal data).",
        ),
        sa.Column(
            "last_host",
            sa.String(length=255),
            nullable=True,
            comment="The host name the reverse DNS lookup of last_address returned; empty when none (personal data).",
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
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
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "device_key ~ '^[0-9a-f]{64}$'", name=op.f("ck_visitor_device_key_format")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_visitor_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("visitor_id", name=op.f("pk_visitor")),
        sa.UniqueConstraint("device_key", name=op.f("uq_visitor_device_key")),
        sa.UniqueConstraint("public_id", name=op.f("uq_visitor_public_id")),
        comment="A person who uses the main screen without an account (application-foundation context, anonymous-visitor capability). Known by the SHA-256 of the random device id its browser keeps; owns its analyses, term lists and votes. Not an account: it has no role and never appears in user management.",
    )
    op.create_index(
        "ix_visitor_active_public_id",
        "visitor",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.add_column(
        "analysis_record",
        sa.Column(
            "asked_by_visitor_id",
            sa.BigInteger(),
            nullable=True,
            comment="The visitor that asked without an account; references visitor.visitor_id. Empty when an account asked.",
        ),
    )
    op.add_column(
        "analysis_record",
        sa.Column(
            "client_address",
            sa.String(length=45),
            nullable=True,
            comment="The visitor's client IP address when it asked; empty for an account (personal data, kept and deleted with the row).",
        ),
    )
    op.add_column(
        "analysis_record",
        sa.Column(
            "client_host",
            sa.String(length=255),
            nullable=True,
            comment="The host name the reverse DNS lookup of client_address returned when it asked; empty when none or for an account (personal data).",
        ),
    )
    op.alter_column(
        "analysis_record",
        "asked_by",
        existing_type=sa.BIGINT(),
        nullable=True,
        comment="The account that asked; references app_user.user_id (never deleted). Empty when a visitor asked; exactly one of asked_by and asked_by_visitor_id is set.",
        existing_comment="The signed-in user who asked; references app_user.user_id (never deleted).",
    )
    op.create_index(
        "ix_analysis_record_tenant_visitor_asked",
        "analysis_record",
        ["tenant_id", "asked_by_visitor_id", "asked_at"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_analysis_record_asked_by_visitor_id_visitor"),
        "analysis_record",
        "visitor",
        ["asked_by_visitor_id"],
        ["visitor_id"],
        ondelete="RESTRICT",
    )
    op.create_table_comment(
        "analysis_record",
        "One analysis job of the data-dictionary context (analysis-records capability): a single question or one term of a term list, from acceptance to its end, with its full answer and steps. question-analysis opens and updates it; a row in a terminal state never changes again. Kept without a time limit and deleted physically only by a manager; is_deleted stays false (Decision 13). Asked by exactly one account or visitor; a visitor's row keeps its address and host name.",
        existing_comment="One analysis job of the data-dictionary context (analysis-records capability): a single question or one term of a term list, from acceptance to its end, with its full answer and steps. question-analysis opens and updates it; a row in a terminal state never changes again. Kept without a time limit and deleted physically only by a manager; is_deleted stays false (Decision 13). No client address or host name is kept.",
        schema=None,
    )
    op.add_column(
        "answer_vote",
        sa.Column(
            "voter_visitor_id",
            sa.BigInteger(),
            nullable=True,
            comment="The visitor that voted; references visitor.visitor_id. Empty for an account.",
        ),
    )
    op.add_column(
        "answer_vote",
        sa.Column(
            "client_address",
            sa.String(length=45),
            nullable=True,
            comment="The visitor's client IP address when it voted; empty for an account (personal data, kept and deleted with the row).",
        ),
    )
    op.add_column(
        "answer_vote",
        sa.Column(
            "client_host",
            sa.String(length=255),
            nullable=True,
            comment="The host name the reverse DNS lookup of client_address returned when it voted; empty when none or for an account (personal data).",
        ),
    )
    op.alter_column(
        "answer_vote",
        "voter_id",
        existing_type=sa.BIGINT(),
        nullable=True,
        comment="The account that voted; references app_user.user_id (never deleted). Empty when a visitor voted; exactly one of voter_id and voter_visitor_id is set.",
        existing_comment="The signed-in user who voted; references app_user.user_id (never deleted).",
    )
    op.create_index(
        "ix_answer_vote_voter_visitor",
        "answer_vote",
        ["voter_visitor_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_answer_vote_voter_visitor_id_visitor"),
        "answer_vote",
        "visitor",
        ["voter_visitor_id"],
        ["visitor_id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "term_list",
        sa.Column(
            "owner_visitor_id",
            sa.BigInteger(),
            nullable=True,
            comment="The visitor that uploaded the list and alone sees, stops and resumes it; references visitor.visitor_id. Empty for an account.",
        ),
    )
    op.add_column(
        "term_list",
        sa.Column(
            "client_address",
            sa.String(length=45),
            nullable=True,
            comment="The visitor's client IP address when it uploaded the list; empty for an account (personal data, kept and deleted with the row).",
        ),
    )
    op.add_column(
        "term_list",
        sa.Column(
            "client_host",
            sa.String(length=255),
            nullable=True,
            comment="The host name the reverse DNS lookup of client_address returned when it uploaded the list; empty when none or for an account (personal data).",
        ),
    )
    op.alter_column(
        "term_list",
        "owner_id",
        existing_type=sa.BIGINT(),
        nullable=True,
        comment="The account that uploaded the list and alone sees, stops and resumes it. Empty when a visitor uploaded it; exactly one of owner_id and owner_visitor_id is set.",
        existing_comment="The user who uploaded the list and alone sees, stops and resumes it.",
    )
    op.create_index(
        "ix_term_list_visitor_created",
        "term_list",
        ["owner_visitor_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_term_list_owner_visitor_id_visitor"),
        "term_list",
        "visitor",
        ["owner_visitor_id"],
        ["visitor_id"],
        ondelete="RESTRICT",
    )
    op.create_table_comment(
        "term_list",
        "A term list of the data-dictionary context (list-search capability): an uploaded one-column Excel list whose terms go one by one through the question analysis. Owned by the uploading account or visitor, the newest five per owner are kept, an older one is deleted physically with its terms (is_deleted stays false). At most one running list per tenant. The uploaded file itself is never stored.",
        existing_comment="A term list of the data-dictionary context (list-search capability): an uploaded one-column Excel list whose terms go one by one through the question analysis. Owned by the uploader, the newest five per person are kept, an older one is deleted physically with its terms (is_deleted stays false). At most one running list per tenant. The uploaded file itself is never stored.",
        schema=None,
    )

    op.create_check_constraint(
        op.f("ck_analysis_record_one_asker"),
        "analysis_record",
        "(asked_by IS NULL) <> (asked_by_visitor_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_answer_vote_one_voter"),
        "answer_vote",
        "(voter_id IS NULL) <> (voter_visitor_id IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_term_list_one_owner"),
        "term_list",
        "(owner_id IS NULL) <> (owner_visitor_id IS NULL)",
    )


def downgrade() -> None:
    op.execute("DELETE FROM term_list WHERE owner_visitor_id IS NOT NULL")
    op.execute("DELETE FROM answer_vote WHERE voter_visitor_id IS NOT NULL")
    op.execute("DELETE FROM analysis_record WHERE asked_by_visitor_id IS NOT NULL")
    op.drop_constraint(op.f("ck_term_list_one_owner"), "term_list", type_="check")
    op.drop_constraint(op.f("ck_answer_vote_one_voter"), "answer_vote", type_="check")
    op.drop_constraint(
        op.f("ck_analysis_record_one_asker"), "analysis_record", type_="check"
    )
    op.create_table_comment(
        "term_list",
        "A term list of the data-dictionary context (list-search capability): an uploaded one-column Excel list whose terms go one by one through the question analysis. Owned by the uploader, the newest five per person are kept, an older one is deleted physically with its terms (is_deleted stays false). At most one running list per tenant. The uploaded file itself is never stored.",
        existing_comment="A term list of the data-dictionary context (list-search capability): an uploaded one-column Excel list whose terms go one by one through the question analysis. Owned by the uploading account or visitor, the newest five per owner are kept, an older one is deleted physically with its terms (is_deleted stays false). At most one running list per tenant. The uploaded file itself is never stored.",
        schema=None,
    )
    op.drop_constraint(
        op.f("fk_term_list_owner_visitor_id_visitor"), "term_list", type_="foreignkey"
    )
    op.drop_index("ix_term_list_visitor_created", table_name="term_list")
    op.alter_column(
        "term_list",
        "owner_id",
        existing_type=sa.BIGINT(),
        nullable=False,
        comment="The user who uploaded the list and alone sees, stops and resumes it.",
        existing_comment="The account that uploaded the list and alone sees, stops and resumes it. Empty when a visitor uploaded it; exactly one of owner_id and owner_visitor_id is set.",
    )
    op.drop_column("term_list", "client_host")
    op.drop_column("term_list", "client_address")
    op.drop_column("term_list", "owner_visitor_id")
    op.drop_constraint(
        op.f("fk_answer_vote_voter_visitor_id_visitor"),
        "answer_vote",
        type_="foreignkey",
    )
    op.drop_index("ix_answer_vote_voter_visitor", table_name="answer_vote")
    op.alter_column(
        "answer_vote",
        "voter_id",
        existing_type=sa.BIGINT(),
        nullable=False,
        comment="The signed-in user who voted; references app_user.user_id (never deleted).",
        existing_comment="The account that voted; references app_user.user_id (never deleted). Empty when a visitor voted; exactly one of voter_id and voter_visitor_id is set.",
    )
    op.drop_column("answer_vote", "client_host")
    op.drop_column("answer_vote", "client_address")
    op.drop_column("answer_vote", "voter_visitor_id")
    op.create_table_comment(
        "analysis_record",
        "One analysis job of the data-dictionary context (analysis-records capability): a single question or one term of a term list, from acceptance to its end, with its full answer and steps. question-analysis opens and updates it; a row in a terminal state never changes again. Kept without a time limit and deleted physically only by a manager; is_deleted stays false (Decision 13). No client address or host name is kept.",
        existing_comment="One analysis job of the data-dictionary context (analysis-records capability): a single question or one term of a term list, from acceptance to its end, with its full answer and steps. question-analysis opens and updates it; a row in a terminal state never changes again. Kept without a time limit and deleted physically only by a manager; is_deleted stays false (Decision 13). Asked by exactly one account or visitor; a visitor's row keeps its address and host name.",
        schema=None,
    )
    op.drop_constraint(
        op.f("fk_analysis_record_asked_by_visitor_id_visitor"),
        "analysis_record",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_analysis_record_tenant_visitor_asked", table_name="analysis_record"
    )
    op.alter_column(
        "analysis_record",
        "asked_by",
        existing_type=sa.BIGINT(),
        nullable=False,
        comment="The signed-in user who asked; references app_user.user_id (never deleted).",
        existing_comment="The account that asked; references app_user.user_id (never deleted). Empty when a visitor asked; exactly one of asked_by and asked_by_visitor_id is set.",
    )
    op.drop_column("analysis_record", "client_host")
    op.drop_column("analysis_record", "client_address")
    op.drop_column("analysis_record", "asked_by_visitor_id")
    op.drop_index(
        "ix_visitor_active_public_id",
        table_name="visitor",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("visitor")
