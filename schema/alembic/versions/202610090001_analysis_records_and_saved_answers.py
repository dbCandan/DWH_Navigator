"""Add the analysis record (analysis_record) and the saved answers (saved_answer).

Expand-only: two new tables, no existing table changes. analysis_record carries the mandatory
block with physical deletion (is_deleted always false); saved_answer has no soft-delete columns and
points at the record that produced it, emptied when that record is deleted. Downgrade drops both
tables: the analysis records and the saved answers (a cache; losing it only means analysing again).

Spec: data-dictionary/PRDs/008-analysis-records and 004-question-analysis (Veri ve geçiş).

Revision ID: 202610090001
Revises: 202610080005
Create Date: 2026-10-09 04:23:52.324691
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610090001"
down_revision: str | None = "202610080005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_record",
        sa.Column("analysis_record_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "public_id",
            sa.String(length=36),
            nullable=False,
            comment="The analysis job's id (UUID) in every analysis and administration endpoint.",
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "asked_by",
            sa.BigInteger(),
            nullable=False,
            comment="The signed-in user who asked; references app_user.user_id (never deleted).",
        ),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            comment="Job state: one of 'queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted'; the last four are terminal.",
        ),
        sa.Column(
            "flow",
            sa.String(length=16),
            nullable=True,
            comment="Who answered, set at the end: one of 'analyst', 'reused', 'unavailable', 'cancelled', 'failed', 'interrupted' (Analist, Önceki cevap, Yapılamadı, Durduruldu, Hata, Yarıda kesildi).",
        ),
        sa.Column(
            "asked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the job was accepted (UTC).",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the job started running (UTC).",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the job ended (UTC).",
        ),
        sa.Column(
            "queue_wait_ms",
            sa.Integer(),
            nullable=True,
            comment="Milliseconds from acceptance to the start.",
        ),
        sa.Column(
            "query",
            sa.Text(),
            nullable=False,
            comment="The question, whole, at most 4000 characters.",
        ),
        sa.Column(
            "fresh",
            sa.Boolean(),
            nullable=False,
            comment="True when a new analysis was asked for (no saved answer).",
        ),
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            comment="'question' (single question) or 'list' (a list term).",
        ),
        sa.Column(
            "list_public_id",
            sa.String(length=36),
            nullable=True,
            comment="For a list term: the list's public_id, kept as a value (no foreign key).",
        ),
        sa.Column(
            "list_file_name",
            sa.String(length=255),
            nullable=True,
            comment="For a list term: the list file's name.",
        ),
        sa.Column(
            "list_position",
            sa.Integer(),
            nullable=True,
            comment="For a list term: its position in the list, from 1.",
        ),
        sa.Column(
            "model",
            sa.String(length=256),
            server_default=sa.text("''"),
            nullable=False,
            comment="Chat model that wrote the answer (for 'reused' the saved answer's model).",
        ),
        sa.Column(
            "verdict",
            sa.String(length=16),
            nullable=True,
            comment="'VAR', 'KISMEN VAR', 'BULUNAMADI' or empty.",
        ),
        sa.Column(
            "summary",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="The answer's summary, its first 500 characters.",
        ),
        sa.Column(
            "table_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="Suggested tables in the answer's order, at most 10 DB.Schema.Object keys.",
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="The full answer of a completed job (question-analysis Requirement 7 and 18): the analysis result with each column's dictionary row inside, so the result and the Excel report are made from it after any later import. Read only by the question-analysis result and report endpoints.",
        ),
        sa.Column(
            "unavailable_reason",
            sa.String(length=500),
            server_default=sa.text("''"),
            nullable=False,
            comment="For 'unavailable': the reason the user saw; never an address or server text.",
        ),
        sa.Column(
            "reused_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="For 'reused': when the saved answer was written (UTC).",
        ),
        sa.Column(
            "reused_query",
            sa.Text(),
            nullable=True,
            comment="For 'reused': the question the saved answer was written to.",
        ),
        sa.Column(
            "reused_match",
            sa.String(length=16),
            nullable=True,
            comment="For 'reused': 'same_question' (aynı soru) or 'same_meaning' (aynı anlam).",
        ),
        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
            comment="For 'failed', 'cancelled' and 'interrupted': the fixed error code.",
        ),
        sa.Column(
            "error_message",
            sa.String(length=500),
            nullable=True,
            comment="The safe Turkish message of the error code; never an exception text.",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=True,
            comment="Milliseconds from acceptance to the end.",
        ),
        sa.Column(
            "llm_calls",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Model calls: the number of 'llm' steps.",
        ),
        sa.Column(
            "prompt_tokens",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Input tokens summed over the call summaries.",
        ),
        sa.Column(
            "completion_tokens",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Output tokens summed over the call summaries.",
        ),
        sa.Column(
            "dictionary_version",
            sa.String(length=64),
            server_default=sa.text("''"),
            nullable=False,
            comment="Version of the dictionary the job's engine was built from.",
        ),
        sa.Column(
            "phase_queue_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the queue (Sırada bekleme) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "phase_saved_answer_lookup_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the saved_answer_lookup (Önceki cevap araması) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "phase_model_check_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the model_check (Model sunucusu kontrolü) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "phase_rule_hints_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the rule_hints (Arama, kural motoru) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "phase_analyst_pick_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the analyst_pick (keys shortlist, family_search) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "phase_analyst_write_ms",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Milliseconds of the analyst_write (key analyst_report) phase: the summed duration of its keyed steps.",
        ),
        sa.Column(
            "steps_truncated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the job had more than 500 steps; the later ones are not kept.",
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="Steps in opening order, at most 500: seq (from 0), parent (seq or null), name (120), kind ('step', 'llm', 'event'), key (null or one of queue, saved_answer_lookup, model_check, rule_hints, shortlist, family_search, analyst_report), start_ms, ms, status ('ok', 'warn', 'error'), detail (300); an 'llm' step adds call (the llm-connection call summary: purpose, integration_public_id, model, started_at, wait_ms, duration_ms, outcome, http_status, requests, adaptations, repaired, prompt_tokens, completion_tokens) and the model check adds check (outcome, http_status, duration_ms, cached). No prompt, reply, address or error body.",
        ),
        sa.Column(
            "search_key",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Turkish-folded question, model, summary, list file name and table keys, written at the end; the text filter searches it. Never returned by the API.",
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
            "(state IN ('queued', 'running')) = (flow IS NULL)",
            name=op.f("ck_analysis_record_flow_only_when_finished"),
        ),
        sa.CheckConstraint(
            "flow IS NULL OR flow IN ('analyst', 'reused', 'unavailable', 'cancelled', 'failed', 'interrupted')",
            name=op.f("ck_analysis_record_flow_allowed"),
        ),
        sa.CheckConstraint(
            "origin IN ('question', 'list')", name=op.f("ck_analysis_record_origin_allowed")
        ),
        sa.CheckConstraint(
            "reused_match IS NULL OR reused_match IN ('same_question', 'same_meaning')",
            name=op.f("ck_analysis_record_reused_match_allowed"),
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name=op.f("ck_analysis_record_state_allowed"),
        ),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('VAR', 'KISMEN VAR', 'BULUNAMADI')",
            name=op.f("ck_analysis_record_verdict_allowed"),
        ),
        sa.CheckConstraint(
            "char_length(query) BETWEEN 1 AND 4000", name=op.f("ck_analysis_record_query_length")
        ),
        sa.CheckConstraint(
            "is_deleted = false", name=op.f("ck_analysis_record_deletion_is_physical")
        ),
        sa.CheckConstraint(
            "list_position IS NULL OR list_position >= 1",
            name=op.f("ck_analysis_record_list_position_from_one"),
        ),
        sa.ForeignKeyConstraint(
            ["asked_by"],
            ["app_user.user_id"],
            name=op.f("fk_analysis_record_asked_by_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_analysis_record_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("analysis_record_id", name=op.f("pk_analysis_record")),
        sa.UniqueConstraint("public_id", name=op.f("uq_analysis_record_public_id")),
        comment="One analysis job of the data-dictionary context (analysis-records capability): a single question or one term of a term list, from acceptance to its end, with its full answer and steps. question-analysis opens and updates it; a row in a terminal state never changes again. Kept without a time limit and deleted physically only by a manager; is_deleted stays false (Decision 13). No client address or host name is kept.",
    )
    op.create_index(
        "ix_analysis_record_tenant_asker_asked",
        "analysis_record",
        ["tenant_id", "asked_by", "asked_at"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_record_tenant_state_asked",
        "analysis_record",
        [
            "tenant_id",
            "state",
            sa.literal_column("asked_at DESC"),
            sa.literal_column("analysis_record_id DESC"),
        ],
        unique=False,
    )
    op.create_table(
        "saved_answer",
        sa.Column("saved_answer_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "query_text",
            sa.String(length=2000),
            nullable=False,
            comment="The question the answer was written to, its first 2000 characters.",
        ),
        sa.Column(
            "text_key",
            sa.Text(),
            nullable=False,
            comment="The question's Turkish-folded words, single-spaced (answer_cache.text_key).",
        ),
        sa.Column(
            "meaning_key",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
            comment="Canonical concept set of the question; empty without a content concept.",
        ),
        sa.Column(
            "fingerprint",
            sa.String(length=16),
            nullable=False,
            comment="First 16 hex digits of the SHA-256 of what the answer depends on: format, dictionary version, word lists, top, prompts, settings and the chat model.",
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The answer in the source's saved form (answer_cache.encode, columns by key), rebuilt from the current dictionary when given again.",
        ),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the answer was written (UTC).",
        ),
        sa.Column(
            "analysis_public_id",
            sa.String(length=36),
            nullable=True,
            comment="The analysis record that produced the answer; empties when it is deleted.",
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
        sa.ForeignKeyConstraint(
            ["analysis_public_id"],
            ["analysis_record.public_id"],
            name=op.f("fk_saved_answer_analysis_public_id_analysis_record"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_saved_answer_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("saved_answer_id", name=op.f("pk_saved_answer")),
        sa.UniqueConstraint("public_id", name=op.f("uq_saved_answer_public_id")),
        sa.UniqueConstraint(
            "tenant_id", "text_key", "fingerprint", name="uq_saved_answer_tenant_text_fingerprint"
        ),
        comment="An analyst answer kept for the same or a same-meaning question (data-dictionary context, question-analysis capability, source ADR-035). Shared by the tenant's users; used only while the fingerprint matches; the newest 2000 are kept and rows are deleted physically (no soft-delete columns, Decision 9). created_by is the user whose question produced the answer.",
    )
    op.create_index(
        op.f("ix_saved_answer_analysis_public_id"),
        "saved_answer",
        ["analysis_public_id"],
        unique=False,
    )
    op.create_index(
        "ix_saved_answer_tenant_fingerprint_answered",
        "saved_answer",
        ["tenant_id", "fingerprint", sa.literal_column("answered_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_saved_answer_tenant_meaning_fingerprint_answered",
        "saved_answer",
        ["tenant_id", "meaning_key", "fingerprint", sa.literal_column("answered_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_answer_tenant_meaning_fingerprint_answered", table_name="saved_answer")
    op.drop_index("ix_saved_answer_tenant_fingerprint_answered", table_name="saved_answer")
    op.drop_index(op.f("ix_saved_answer_analysis_public_id"), table_name="saved_answer")
    op.drop_table("saved_answer")
    op.drop_index("ix_analysis_record_tenant_state_asked", table_name="analysis_record")
    op.drop_index("ix_analysis_record_tenant_asker_asked", table_name="analysis_record")
    op.drop_table("analysis_record")
