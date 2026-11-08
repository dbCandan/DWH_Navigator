/**
 * The dictionary sync's contract (data-dictionary/PRDs/011-dictionary-sync/plan.md, API sözleşmesi).
 * Written by hand until the OpenAPI document and `api.d.ts` carry these endpoints.
 */
export interface DictionaryPerson {
  public_id: string;
  display_name: string;
}

export interface DictionarySource {
  configured: boolean;
  host: string;
  port: number;
  database: string;
  username: string;
  has_password: boolean;
  encrypt: boolean;
  updated_at: string | null;
}

/** Without `password` the saved one stays; no answer ever carries it. */
export interface DictionarySourceInput {
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  encrypt: boolean;
}

export interface DictionarySourceTest {
  ok: boolean;
  message: string;
  table_count: number;
  column_count: number;
  last_change_at: string | null;
  /** The databases the dictionary names but the server could not reach, when the answer says so. */
  missing_databases?: string[];
}

export type SyncRunKind = 'guncelleme' | 'geri_donus';
export type SyncRunStatus = 'running' | 'completed' | 'no_change' | 'pending_approval' | 'rejected' | 'failed' | 'interrupted';
export type SyncRunPhase =
  | 'reading'
  | 'comparing'
  | 'filling'
  | 'describing'
  | 'verifying'
  | 'scoring'
  | 'indexing'
  | 'done';

export interface SyncCounts {
  tables_added: number;
  tables_removed: number;
  tables_changed: number;
  tables_excluded: number;
  tables_corrected: number;
  columns_added: number;
  columns_removed: number;
  columns_changed: number;
  columns_excluded: number;
  columns_corrected: number;
  fields_filled: number;
  /** Fields the owner's rules cleaned (doubt, wording, value lists, key columns). */
  fields_normalized?: number;
  /** Rows the update looked at: new, source text changed, computation changed. */
  scope_tables?: number;
  scope_columns?: number;
  scope_code_changed?: number;
  fields_empty: number;
  model_calls: number;
  model_failures: number;
  warnings: number;
}

export interface SyncRunSummary {
  public_id: string;
  kind: SyncRunKind;
  status: SyncRunStatus;
  phase: SyncRunPhase;
  progress_done: number;
  progress_total: number;
  started_at: string;
  finished_at: string | null;
  started_by: DictionaryPerson | null;
  previous_version: string;
  new_version: string;
  model: string;
  counts: SyncCounts;
  /** The score card an admin decides on; empty for runs before it existed. */
  score?: SyncScore;
  error_code: string;
  error_message: string;
}

export interface SyncSuggestion {
  public_id: string;
  kind: 'term' | 'stopword';
  value: string;
  equivalents: string[];
  note: string;
  status: 'pending' | 'applied';
}

export interface SyncRunDetail extends SyncRunSummary {
  warnings: string[];
  suggestions: SyncSuggestion[];
}

export const SYNC_CHANGE_KINDS = [
  'table_added',
  'table_removed',
  'table_changed',
  'table_excluded',
  'table_corrected',
  'column_added',
  'column_removed',
  'column_changed',
  'column_excluded',
  'column_corrected',
  'table_normalized',
  'column_normalized',
  'table_admin_edited',
  'column_admin_edited',
] as const;

export type SyncChangeKind = (typeof SYNC_CHANGE_KINDS)[number];

/** For `*_corrected`, `old_value` is the source's spelling and `new_value` the catalog's. */
export interface SyncChange {
  kind: SyncChangeKind;
  table_key: string;
  column_name: string;
  field: string;
  old_value: string;
  new_value: string;
  origin: 'kaynak' | 'model' | 'onceki' | 'duzenleme' | 'yonetici' | '';
}

export interface SyncPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DictionaryVersion {
  public_id: string;
  version: string;
  status: 'active' | 'previous' | 'pending';
  channel: string;
  imported_at: string;
  imported_by: DictionaryPerson | null;
  object_count: number;
  column_count: number;
  run_public_id: string | null;
  expires_at: string | null;
  can_restore: boolean;
}

export type SyncScoreVerdict = 'onaylanabilir' | 'incelenmeli' | 'reddedilmeli';

export interface SyncScoreCheck {
  count: number;
  examples: string[];
}

export interface SyncJudgedRow {
  table: string;
  column: string;
  verdict: 'dogru' | 'kucuk' | 'hatali';
  reason: string;
}

/** dictionary_curation.score: every check of an update, and its recommendation. */
export interface SyncScore {
  score?: number;
  verdict?: SyncScoreVerdict;
  checks?: Record<string, SyncScoreCheck>;
  failed_checks?: string[];
  judge?: {
    sample: number;
    population: number;
    right: number;
    minor: number;
    wrong: number;
    wrong_interval: [number, number];
    failures: number;
    wrong_rows: SyncJudgedRow[];
  };
  model?: {calls: number; failures: number; failure_rate: number};
  rules?: {normalized_fields: number};
  scope?: Record<string, number>;
  admin_edits?: number;
}

/** The fields an admin may write in a version waiting for approval. */
export const COLUMN_EDIT_FIELDS = ['ColumnDescription', 'Synonyms', 'Summary', 'Role'] as const;
export const OBJECT_EDIT_FIELDS = ['ObjectDescription', 'Grain', 'KeyColumns', 'TimeColumns', 'BusinessDomain'] as const;
export type SyncEditField = (typeof COLUMN_EDIT_FIELDS)[number] | (typeof OBJECT_EDIT_FIELDS)[number];

export interface SyncRecordEdit {
  table_key: string;
  column_name: string;
  field: SyncEditField;
  value: string;
}

/** GET /dictionary/sync/preview: what an update would look at, before it starts. */
export interface SyncPreview {
  has_changes: boolean;
  scope: Record<string, number>;
  tables_needing_model: number;
  rows_to_describe: number;
  objects_to_describe: number;
  model_calls: number;
  average_call_seconds: number;
  estimated_seconds: number;
  requires_approval: boolean;
}
