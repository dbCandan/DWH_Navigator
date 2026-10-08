"""The term dictionary and stopword lists (data-dictionary 002-vocabulary-management).

Each list has one header row per tenant, addressed by its fixed name (``terms``, ``stopwords``),
and ordered item rows. A change soft-deletes every item row of the list and inserts the new ones
in one transaction; item rows are never addressed from outside and carry no public_id (Decision
3). Soft-deleted item rows are never read again (Decision 4).
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin
from app.domain.vocabulary import (
    MAX_DOMAIN_LENGTH,
    MAX_EQUIVALENTS,
    MAX_GROUP_LENGTH,
    MAX_NOTE_LENGTH,
    MAX_STOPWORD_LENGTH,
    MAX_TERM_LENGTH,
)


class VocabularyListHeader(AuditSoftDeleteMixin, Base):
    __tablename__ = "vocabulary_list"
    __table_args__ = (
        UniqueConstraint("tenant_id", "public_id", name="uq_vocabulary_list_tenant_public_id"),
        Index(
            "ix_vocabulary_list_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("public_id IN ('terms', 'stopwords')", name="public_id_allowed"),
        CheckConstraint(
            "last_source IN ('baslangic', 'ekran', 'excel')", name="last_source_allowed"
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("content_digest ~ '^[0-9a-f]{64}$'", name="content_digest_format"),
        {
            "comment": (
                "Header of one word list of the data-dictionary context's vocabulary-management "
                "capability: the term dictionary ('terms') or the stopwords ('stopwords'), one "
                "row per tenant. A list changes only as a whole; every written change raises the "
                "revision by one. updated_at and updated_by are the last change and its user "
                "(empty for the seed)."
            )
        },
    )

    vocabulary_list_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "The list's fixed name, unique per tenant; code reflection "
            "app.domain.vocabulary.VocabularyList: 'terms' = term dictionary, 'stopwords' = "
            "stopwords."
        ),
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1 for the seed list; raised by one by every written change.",
    )
    content_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "SHA-256 of the ordered items' stable JSON (app.domain.vocabulary.list_digest); "
            "a save with the same digest writes nothing."
        ),
    )
    last_source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Origin of the last change; code reflection app.domain.vocabulary.VocabularySource: "
            "'baslangic' = seed migration, 'ekran' = admin screen save, 'excel' = workbook import."
        ),
    )


class VocabularyTerm(AuditSoftDeleteMixin, Base):
    __tablename__ = "vocabulary_term"
    __table_args__ = (
        Index(
            "uq_vocabulary_term_tenant_term_key",
            "tenant_id",
            "term_key",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "uq_vocabulary_term_tenant_position",
            "tenant_id",
            "position",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint(f"char_length(term) BETWEEN 1 AND {MAX_TERM_LENGTH}", name="term_length"),
        CheckConstraint(f"char_length(domain) <= {MAX_DOMAIN_LENGTH}", name="domain_length"),
        CheckConstraint(f"char_length(note) <= {MAX_NOTE_LENGTH}", name="note_length"),
        CheckConstraint(f"cardinality(equivalents) <= {MAX_EQUIVALENTS}", name="equivalents_count"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        {
            "comment": (
                "One term group of a tenant's term dictionary (vocabulary-management): the term "
                "and its equivalents; every member also searches for the others. Rows of the "
                "current list are the non-deleted ones; a change soft-deletes them all and "
                "inserts the new list. created_by is the user who saved the list (empty for the "
                "seed)."
            )
        },
    )

    vocabulary_term_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    vocabulary_list_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vocabulary_list.vocabulary_list_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The term list header; references vocabulary_list.vocabulary_list_id.",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment=(
            "0-based order in the list; term expansion reads the groups in this order and the "
            "saved-answer fingerprint holds them in it."
        ),
    )
    term: Mapped[str] = mapped_column(
        String(MAX_TERM_LENGTH), nullable=False, comment="The term as entered, trimmed."
    )
    term_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "The term with the application's Turkish folding (app.domain.turkish_text.fold); "
            "unique among the tenant's current terms."
        ),
    )
    equivalents: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        comment="Ordered equivalents, each at most 200 characters, at most 100.",
    )
    domain: Mapped[str] = mapped_column(
        String(MAX_DOMAIN_LENGTH),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Grouping word chosen by the administrator; not used by the search.",
    )
    note: Mapped[str] = mapped_column(
        String(MAX_NOTE_LENGTH),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Optional explanation; not used by the search.",
    )


class VocabularyStopword(AuditSoftDeleteMixin, Base):
    __tablename__ = "vocabulary_stopword"
    __table_args__ = (
        Index(
            "uq_vocabulary_stopword_tenant_position",
            "tenant_id",
            "position",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint(
            f"char_length(word) BETWEEN 1 AND {MAX_STOPWORD_LENGTH}", name="word_length"
        ),
        CheckConstraint(f"char_length(group_name) <= {MAX_GROUP_LENGTH}", name="group_name_length"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        {
            "comment": (
                "One stopword of a tenant (vocabulary-management): a single word the search "
                "ignores. Rows of the current list are the non-deleted ones; a change "
                "soft-deletes them all and inserts the new list. word_key is not unique: the "
                "seed keeps folded-equal words in separate rows (Decision 10). created_by is the "
                "user who saved the list (empty for the seed)."
            )
        },
    )

    vocabulary_stopword_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    vocabulary_list_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vocabulary_list.vocabulary_list_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The stopword list header; references vocabulary_list.vocabulary_list_id.",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="0-based order in the list, as the screen shows it.",
    )
    word: Mapped[str] = mapped_column(
        String(MAX_STOPWORD_LENGTH),
        nullable=False,
        comment="The word as entered, trimmed.",
    )
    word_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="The word with the application's Turkish folding (app.domain.turkish_text.fold).",
    )
    group_name: Mapped[str] = mapped_column(
        String(MAX_GROUP_LENGTH),
        nullable=False,
        default="",
        server_default=text("''"),
        comment="Why the word is on the list; arranges the screen, not the search.",
    )
