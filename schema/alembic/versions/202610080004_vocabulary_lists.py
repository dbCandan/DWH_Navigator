"""Add the term dictionary and stopword lists with their seed lists.

Expand-only: it adds vocabulary_list, vocabulary_term and vocabulary_stopword and changes no
existing table. It then loads the seed lists once per database (Requirement 9): the byte copies
of the source's data/terms.jsonl (45 groups) and data/stopwords.jsonl (106 words) under
schema/alembic/seed/vocabulary, after their SHA-256 digests are verified, as they are and in file
order, revision 1, source 'baslangic', no user. A list whose header already exists is left alone.
Downgrade drops the three tables and every list.

Spec: data-dictionary/PRDs/002-vocabulary-management (Veri ve geçiş, Requirement 9).

Revision ID: 202610080004
Revises: 202610080003
Create Date: 2026-10-08 19:52:29.608816
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610080004"
down_revision: str | None = "202610080003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DIRECTORY = Path(__file__).resolve().parents[1] / "seed" / "vocabulary"
# Requirement 9: the byte copies of the source's lists at 76e21a3; a different file stops here.
SEED_FILES = {
    "terms": (
        "terms.jsonl",
        "5d8e48cb8372814f34097ca76fe457831980b729181c939dac234852856e078b",
    ),
    "stopwords": (
        "stopwords.jsonl",
        "0e9096525c2a6ba6d843cc23563dae8b3337c0c4ce77f52766aae8edd862595d",
    ),
}
logger = logging.getLogger("alembic.runtime.migration.vocabulary")


def upgrade() -> None:
    op.create_table(
        "vocabulary_list",
        sa.Column(
            "vocabulary_list_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "public_id",
            sa.Text(),
            nullable=False,
            comment="The list's fixed name, unique per tenant; code reflection app.domain.vocabulary.VocabularyList: 'terms' = term dictionary, 'stopwords' = stopwords.",
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            comment="1 for the seed list; raised by one by every written change.",
        ),
        sa.Column(
            "content_digest",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 of the ordered items' stable JSON (app.domain.vocabulary.list_digest); a save with the same digest writes nothing.",
        ),
        sa.Column(
            "last_source",
            sa.String(length=16),
            nullable=False,
            comment="Origin of the last change; code reflection app.domain.vocabulary.VocabularySource: 'baslangic' = seed migration, 'ekran' = admin screen save, 'excel' = workbook import.",
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_vocabulary_list_content_digest_format"),
        ),
        sa.CheckConstraint(
            "last_source IN ('baslangic', 'ekran', 'excel')",
            name=op.f("ck_vocabulary_list_last_source_allowed"),
        ),
        sa.CheckConstraint(
            "public_id IN ('terms', 'stopwords')",
            name=op.f("ck_vocabulary_list_public_id_allowed"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_vocabulary_list_revision_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_vocabulary_list_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("vocabulary_list_id", name=op.f("pk_vocabulary_list")),
        sa.UniqueConstraint("tenant_id", "public_id", name="uq_vocabulary_list_tenant_public_id"),
        comment="Header of one word list of the data-dictionary context's vocabulary-management capability: the term dictionary ('terms') or the stopwords ('stopwords'), one row per tenant. A list changes only as a whole; every written change raises the revision by one. updated_at and updated_by are the last change and its user (empty for the seed).",
    )
    op.create_index(
        "ix_vocabulary_list_active_public_id",
        "vocabulary_list",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_vocabulary_list_tenant_id"),
        "vocabulary_list",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "vocabulary_stopword",
        sa.Column(
            "vocabulary_stopword_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "vocabulary_list_id",
            sa.BigInteger(),
            nullable=False,
            comment="The stopword list header; references vocabulary_list.vocabulary_list_id.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="0-based order in the list, as the screen shows it.",
        ),
        sa.Column(
            "word",
            sa.String(length=100),
            nullable=False,
            comment="The word as entered, trimmed.",
        ),
        sa.Column(
            "word_key",
            sa.Text(),
            nullable=False,
            comment="The word with the application's Turkish folding (app.domain.turkish_text.fold).",
        ),
        sa.Column(
            "group_name",
            sa.String(length=200),
            server_default=sa.text("''"),
            nullable=False,
            comment="Why the word is on the list; arranges the screen, not the search.",
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "char_length(group_name) <= 200",
            name=op.f("ck_vocabulary_stopword_group_name_length"),
        ),
        sa.CheckConstraint(
            "char_length(word) BETWEEN 1 AND 100",
            name=op.f("ck_vocabulary_stopword_word_length"),
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_vocabulary_stopword_position_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_vocabulary_stopword_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_list_id"],
            ["vocabulary_list.vocabulary_list_id"],
            name=op.f("fk_vocabulary_stopword_vocabulary_list_id_vocabulary_list"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("vocabulary_stopword_id", name=op.f("pk_vocabulary_stopword")),
        comment="One stopword of a tenant (vocabulary-management): a single word the search ignores. Rows of the current list are the non-deleted ones; a change soft-deletes them all and inserts the new list. word_key is not unique: the seed keeps folded-equal words in separate rows (Decision 10). created_by is the user who saved the list (empty for the seed).",
    )
    op.create_index(
        op.f("ix_vocabulary_stopword_tenant_id"),
        "vocabulary_stopword",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vocabulary_stopword_vocabulary_list_id"),
        "vocabulary_stopword",
        ["vocabulary_list_id"],
        unique=False,
    )
    op.create_index(
        "uq_vocabulary_stopword_tenant_position",
        "vocabulary_stopword",
        ["tenant_id", "position"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "vocabulary_term",
        sa.Column(
            "vocabulary_term_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "vocabulary_list_id",
            sa.BigInteger(),
            nullable=False,
            comment="The term list header; references vocabulary_list.vocabulary_list_id.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="0-based order in the list; term expansion reads the groups in this order and the saved-answer fingerprint holds them in it.",
        ),
        sa.Column(
            "term",
            sa.String(length=200),
            nullable=False,
            comment="The term as entered, trimmed.",
        ),
        sa.Column(
            "term_key",
            sa.Text(),
            nullable=False,
            comment="The term with the application's Turkish folding (app.domain.turkish_text.fold); unique among the tenant's current terms.",
        ),
        sa.Column(
            "equivalents",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            comment="Ordered equivalents, each at most 200 characters, at most 100.",
        ),
        sa.Column(
            "domain",
            sa.String(length=100),
            server_default=sa.text("''"),
            nullable=False,
            comment="Grouping word chosen by the administrator; not used by the search.",
        ),
        sa.Column(
            "note",
            sa.String(length=1000),
            server_default=sa.text("''"),
            nullable=False,
            comment="Optional explanation; not used by the search.",
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
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "cardinality(equivalents) <= 100",
            name=op.f("ck_vocabulary_term_equivalents_count"),
        ),
        sa.CheckConstraint(
            "char_length(domain) <= 100", name=op.f("ck_vocabulary_term_domain_length")
        ),
        sa.CheckConstraint(
            "char_length(note) <= 1000", name=op.f("ck_vocabulary_term_note_length")
        ),
        sa.CheckConstraint(
            "char_length(term) BETWEEN 1 AND 200",
            name=op.f("ck_vocabulary_term_term_length"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_vocabulary_term_position_not_negative")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_vocabulary_term_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_list_id"],
            ["vocabulary_list.vocabulary_list_id"],
            name=op.f("fk_vocabulary_term_vocabulary_list_id_vocabulary_list"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("vocabulary_term_id", name=op.f("pk_vocabulary_term")),
        comment="One term group of a tenant's term dictionary (vocabulary-management): the term and its equivalents; every member also searches for the others. Rows of the current list are the non-deleted ones; a change soft-deletes them all and inserts the new list. created_by is the user who saved the list (empty for the seed).",
    )
    op.create_index(
        op.f("ix_vocabulary_term_tenant_id"),
        "vocabulary_term",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vocabulary_term_vocabulary_list_id"),
        "vocabulary_term",
        ["vocabulary_list_id"],
        unique=False,
    )
    op.create_index(
        "uq_vocabulary_term_tenant_position",
        "vocabulary_term",
        ["tenant_id", "position"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "uq_vocabulary_term_tenant_term_key",
        "vocabulary_term",
        ["tenant_id", "term_key"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    load_seed_lists()


def downgrade() -> None:
    op.drop_index(
        "uq_vocabulary_term_tenant_term_key",
        table_name="vocabulary_term",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(
        "uq_vocabulary_term_tenant_position",
        table_name="vocabulary_term",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(op.f("ix_vocabulary_term_vocabulary_list_id"), table_name="vocabulary_term")
    op.drop_index(op.f("ix_vocabulary_term_tenant_id"), table_name="vocabulary_term")
    op.drop_table("vocabulary_term")
    op.drop_index(
        "uq_vocabulary_stopword_tenant_position",
        table_name="vocabulary_stopword",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index(
        op.f("ix_vocabulary_stopword_vocabulary_list_id"),
        table_name="vocabulary_stopword",
    )
    op.drop_index(op.f("ix_vocabulary_stopword_tenant_id"), table_name="vocabulary_stopword")
    op.drop_table("vocabulary_stopword")
    op.drop_index(op.f("ix_vocabulary_list_tenant_id"), table_name="vocabulary_list")
    op.drop_index(
        "ix_vocabulary_list_active_public_id",
        table_name="vocabulary_list",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("vocabulary_list")


def _event(list_name: str, items: int, outcome: str) -> None:
    """The ``vocabulary.seed`` event of the migration Job: list, item count and outcome only."""

    fields = {
        "event": "vocabulary.seed",
        "list": list_name,
        "items": items,
        "outcome": outcome,
    }
    logger.info("vocabulary.seed %s", json.dumps(fields, sort_keys=True))


def _seed_items(list_name: str, directory: Path) -> list[dict[str, Any]]:
    name, digest = SEED_FILES[list_name]
    data = (directory / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        _event(list_name, 0, "failed")
        raise RuntimeError(f"seed list {name} does not match its recorded SHA-256 digest")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if list_name == "terms":
        return [
            {
                "term": row["term"],
                "equivalents": list(row["equivalents"]),
                "domain": row.get("domain", ""),
                "note": row.get("note", ""),
            }
            for row in rows
        ]
    return [{"word": row["word"], "group": row.get("group", "")} for row in rows]


def load_seed_lists(directory: Path = SEED_DIRECTORY) -> None:
    """Load each seed list once per database: as it is, in file order, without the save checks
    (Decision 10). A tenant whose list header exists, even of an empty list, keeps its list.
    """

    # The application's Turkish folding and list digest, so the keys and the digest are the ones
    # every later save computes.
    from app.domain.turkish_text import fold
    from app.domain.vocabulary import list_digest

    bind = op.get_bind()
    tenants = bind.execute(sa.text("SELECT tenant_id FROM tenant WHERE code = 'platform'")).all()
    for (tenant_id,) in tenants:
        for list_name in SEED_FILES:
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM vocabulary_list WHERE tenant_id = :tenant AND public_id = :name"
                ),
                {"tenant": tenant_id, "name": list_name},
            ).first()
            if exists is not None:
                _event(list_name, 0, "skipped")
                continue
            items = _seed_items(list_name, directory)
            list_id = bind.execute(
                sa.text(
                    "INSERT INTO vocabulary_list (public_id, tenant_id, revision, content_digest, "
                    "last_source) VALUES (:name, :tenant, 1, :digest, 'baslangic') "
                    "RETURNING vocabulary_list_id"
                ),
                {"name": list_name, "tenant": tenant_id, "digest": list_digest(items)},
            ).scalar_one()
            if list_name == "terms":
                bind.execute(
                    sa.text(
                        "INSERT INTO vocabulary_term (tenant_id, vocabulary_list_id, position, term, "
                        "term_key, equivalents, domain, note) VALUES (:tenant, :list, :position, "
                        ":term, :key, :equivalents, :domain, :note)"
                    ),
                    [
                        {
                            "tenant": tenant_id,
                            "list": list_id,
                            "position": position,
                            "term": item["term"],
                            "key": fold(item["term"]),
                            "equivalents": item["equivalents"],
                            "domain": item["domain"],
                            "note": item["note"],
                        }
                        for position, item in enumerate(items)
                    ],
                )
            else:
                bind.execute(
                    sa.text(
                        "INSERT INTO vocabulary_stopword (tenant_id, vocabulary_list_id, position, "
                        "word, word_key, group_name) VALUES (:tenant, :list, :position, :word, "
                        ":key, :group)"
                    ),
                    [
                        {
                            "tenant": tenant_id,
                            "list": list_id,
                            "position": position,
                            "word": item["word"],
                            "key": fold(item["word"]),
                            "group": item["group"],
                        }
                        for position, item in enumerate(items)
                    ],
                )
            _event(list_name, len(items), "loaded")
