import {vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {setConfirmHandler} from '@/lib/confirm';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {DictionaryService} from '@/services/dictionary';
import {DictionarySyncService} from '@/services/dictionarySync';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {SavedAnswersService} from '@/services/savedAnswers';
import {SearchSettingsService} from '@/services/searchSettings';
import {VocabularyService} from '@/services/vocabulary';
import type {DictionaryState, DictionaryTable} from '@/types/dictionary';
import type {DictionarySource, DictionaryVersion, SyncChange, SyncCounts, SyncRunDetail, SyncRunSummary} from '@/types/dictionarySync';
import type {RecordDetail, RecordPage, RecordRow, RecordSummary} from '@/types/records';
import type {SearchIndexState, SearchSettingField, SearchSettings} from '@/types/search';
import {llmState} from './llm';
import type {StopwordItem, TermItem, VocabularyListState} from '@/types/vocabulary';

const field = (key: string, label: string, overrides: Partial<SearchSettingField> = {}): SearchSettingField => ({
  key,
  label,
  help: '',
  type: 'int',
  format: null,
  min: 0,
  max: 100,
  step: 1,
  effect: 'immediate',
  advanced: false,
  ...overrides,
});

/** A trimmed copy of the search settings schema (search-settings Requirement 1). */
export function searchSettings(values: Record<string, boolean | number> = {}): SearchSettings {
  const defaults = {
    'analyst.shortlist': 14,
    'analyst.min_confidence': 0.5,
    'analyst.max_tokens': 8000,
    'expansion.enabled': true,
    'search.bm25.k1': 1.2,
    'cache.enabled': true,
    'cache.max_age_days': 30,
  };
  return {
    sections: [
      {
        id: 'analyst',
        page: 'search',
        title: 'Analist',
        intro: 'Cevabı sohbet modeli yazar.',
        advanced: false,
        fields: [
          field('analyst.shortlist', 'Kolonları okunacak aday tablo sayısı', {help: '1. adımda modelin seçebileceği en fazla tablo.', min: 3, max: 30}),
          field('analyst.min_confidence', 'Gösterilecek en düşük model güveni', {type: 'float', format: 'pct', min: 0, max: 1, step: 0.05}),
          field('analyst.max_tokens', 'Cevap için en fazla token', {min: 1000, max: 32000, step: 500, advanced: true}),
        ],
      },
      {
        id: 'terms',
        page: 'search',
        title: 'Eş anlamlılar ve terimler',
        intro: '',
        advanced: false,
        fields: [field('expansion.enabled', 'Kurumsal terim sözlüğünü kullan', {type: 'bool', min: null, max: null, step: null, effect: 'reindex'})],
      },
      {
        id: 'words',
        page: 'search',
        title: 'Kelime araması',
        intro: 'Kolon adı, eş anlamlı ve açıklamalarda BM25 araması.',
        advanced: true,
        fields: [
          field('search.bm25.k1', 'BM25 k1', {type: 'float', min: 0.1, max: 3, step: 0.1, effect: 'reindex', advanced: true, help: 'Aynı kelimenin tekrarı ne kadar sayılsın.'}),
        ],
      },
      {
        id: 'cache',
        page: 'data',
        title: 'Önceki cevaplar',
        intro: 'Aynı ya da aynı anlamdaki soru analiz yerine kayıtlı cevabı alır.',
        advanced: false,
        fields: [
          field('cache.enabled', 'Önceki cevapları kullan', {type: 'bool', min: null, max: null, step: null}),
          field('cache.max_age_days', 'Cevap kaç gün geçerli', {min: 0, max: 365, advanced: true}),
        ],
      },
    ],
    values: {...defaults, ...values},
    defaults,
  };
}

export function indexState(overrides: Partial<SearchIndexState> = {}): SearchIndexState {
  return {
    state: 'ready',
    stale_inputs: [],
    columns: 120,
    objects: 12,
    dictionary_version: 'abcdef123456-130',
    built_at: '2026-10-08T09:00:00Z',
    build_ms: 850,
    trigger: 'dictionary',
    running: null,
    last_failure: null,
    ...overrides,
  };
}

export const EMPTY_DICTIONARY: DictionaryState = {active: null, previous: null, index_dictionary_version: ''};

export function dictionaryState(overrides: Partial<NonNullable<DictionaryState['active']>> = {}, indexVersion?: string): DictionaryState {
  const active = {
    public_id: '00000000-0000-4000-8000-0000000000d1',
    version: 'abcdef123456-130',
    source_name: 'sozluk_sentetik.xlsx',
    imported_at: '2026-10-08T09:00:00Z',
    imported_by: null,
    channel: 'arayuz' as const,
    object_count: 12,
    column_count: 120,
    row_count: 130,
    warning_count: 0,
    warnings: [],
    ...overrides,
  };
  return {active, previous: null, index_dictionary_version: indexVersion ?? active.version};
}

export const table = (key: string, overrides: Partial<DictionaryTable> = {}): DictionaryTable => ({
  key,
  name: key.split('.').pop() ?? key,
  group: '',
  domain: '',
  description: '',
  grain: '',
  columns: 3,
  ...overrides,
});

export const dictionarySource = (overrides: Partial<DictionarySource> = {}): DictionarySource => ({
  configured: false,
  host: '',
  port: 1433,
  database: '',
  username: '',
  has_password: false,
  encrypt: true,
  updated_at: null,
  ...overrides,
});

const NO_COUNTS: SyncCounts = {
  tables_added: 0,
  tables_removed: 0,
  tables_changed: 0,
  tables_excluded: 0,
  tables_corrected: 0,
  columns_added: 0,
  columns_removed: 0,
  columns_changed: 0,
  columns_excluded: 0,
  columns_corrected: 0,
  fields_filled: 0,
  fields_empty: 0,
  model_calls: 0,
  model_failures: 0,
  warnings: 0,
};

type WithCounts<T> = Partial<Omit<T, 'counts'>> & {counts?: Partial<SyncCounts>};

/** A run's summary; a finished update unless a test says otherwise. */
export const syncRun = (overrides: WithCounts<SyncRunSummary> = {}): SyncRunSummary => ({
  public_id: '00000000-0000-4000-8000-0000000000e1',
  kind: 'guncelleme',
  status: 'completed',
  phase: 'done',
  progress_done: 0,
  progress_total: 0,
  started_at: '2026-10-08T09:00:00Z',
  finished_at: '2026-10-08T09:05:00Z',
  started_by: {public_id: '00000000-0000-4000-8000-0000000000b1', display_name: 'Ali Veli'},
  previous_version: 'aaaaaaaaaaaa-100',
  new_version: 'bbbbbbbbbbbb-130',
  model: 'org/qwen-32b',
  error_code: '',
  error_message: '',
  ...overrides,
  counts: {...NO_COUNTS, ...overrides.counts},
});

export const syncDetail = (overrides: WithCounts<SyncRunDetail> = {}): SyncRunDetail => ({
  warnings: [],
  suggestions: [],
  ...overrides,
  ...syncRun(overrides),
});

export const syncChange = (overrides: Partial<SyncChange> = {}): SyncChange => ({
  kind: 'table_added',
  table_key: 'EDWDM.DBO.vMusteri',
  column_name: '',
  field: '',
  old_value: '',
  new_value: '',
  origin: '',
  ...overrides,
});

export const dictionaryVersion = (overrides: Partial<DictionaryVersion> = {}): DictionaryVersion => ({
  public_id: '00000000-0000-4000-8000-0000000000f1',
  version: 'aaaaaaaaaaaa-100',
  status: 'previous',
  channel: 'kaynak',
  imported_at: '2026-10-01T09:00:00Z',
  imported_by: null,
  object_count: 10,
  column_count: 90,
  run_public_id: null,
  expires_at: '2026-11-01T09:00:00Z',
  can_restore: true,
  ...overrides,
});

export const termList = (items: TermItem[], revision = 1): VocabularyListState => ({list: 'terms', revision, items});
export const stopList = (items: StopwordItem[], revision = 1): VocabularyListState => ({list: 'stopwords', revision, items});

export const SNAPSHOT_AT = '2026-10-08T12:00:00Z';

/** A list answer of the analysis records (analysis-records Requirement 6). */
export function recordPage(overrides: Partial<RecordPage> = {}): RecordPage {
  return {items: [], total: 0, page: 1, page_size: 150, snapshot_at: SNAPSHOT_AT, ...overrides};
}

let recordCount = 0;

/** A finished record's list row (analysis-records Requirement 6); synthetic people and tables. */
export function recordRow(query: string, overrides: Partial<RecordRow> = {}): RecordRow {
  return {
    public_id: `0b6f6f3e-3e0a-4c58-9a3a-${String(++recordCount).padStart(12, '0')}`,
    asked_at: '2026-10-08T09:00:00Z',
    asked_by: {public_id: '00000000-0000-4000-8000-0000000000b1', display_name: 'Ali Veli', kind: 'account'},
    query,
    origin: 'question',
    list_public_id: null,
    list_file_name: null,
    list_position: null,
    flow: 'analyst',
    model: 'org/qwen-32b',
    verdict: 'VAR',
    table_keys: ['DWH.Ornek.vCustomer'],
    unavailable_reason: '',
    error: null,
    duration_ms: 12000,
    ...overrides,
  };
}

/** A finished record's detail (analysis-records Requirement 10). */
export function recordDetail(row: RecordRow, overrides: Partial<RecordDetail> = {}): RecordDetail {
  return {
    ...row,
    summary: '',
    reused: null,
    llm_calls: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    dictionary_version: 'abcdef123456-130',
    started_at: row.asked_at,
    finished_at: row.asked_at,
    queue_wait_ms: 0,
    phases: {queue: 0, saved_answer_lookup: 0, model_check: 0, rule_hints: 0, analyst_pick: 0, analyst_write: 0},
    steps_truncated: false,
    steps: [],
    ...overrides,
  };
}

/** A summary of no records (analysis-records Requirement 7). */
export function recordSummary(overrides: Partial<RecordSummary> = {}): RecordSummary {
  return {
    count: 0,
    newest_at: null,
    with_result: 0,
    with_tables: 0,
    flows: {analyst: 0, reused: 0, unavailable: 0, cancelled: 0, failed: 0, interrupted: 0},
    analyst_p50_ms: null,
    analyst_p90_ms: null,
    p50_ms: null,
    p90_ms: null,
    max_ms: null,
    phases: [],
    llm_calls: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    askers: [],
    snapshot_at: SNAPSHOT_AT,
    ...overrides,
  };
}

/** The admin shell's reads answered with an empty, settled installation unless a test says otherwise. */
export function serveAdminDefaults() {
  vi.spyOn(LlmIntegrationService, 'list').mockResolvedValue(llmState());
  vi.spyOn(SearchSettingsService, 'settings').mockResolvedValue(searchSettings());
  vi.spyOn(SearchSettingsService, 'index').mockResolvedValue(indexState({columns: 0, objects: 0, dictionary_version: ''}));
  vi.spyOn(DictionaryService, 'state').mockResolvedValue(EMPTY_DICTIONARY);
  vi.spyOn(DictionaryService, 'tables').mockResolvedValue([]);
  vi.spyOn(DictionarySyncService, 'source').mockResolvedValue(dictionarySource());
  vi.spyOn(DictionarySyncService, 'runs').mockResolvedValue({items: [], total: 0, page: 1, page_size: 20});
  vi.spyOn(DictionarySyncService, 'versions').mockResolvedValue([]);
  vi.spyOn(DictionarySyncService, 'changes').mockResolvedValue({items: [], total: 0, page: 1, page_size: 50});
  vi.spyOn(SavedAnswersService, 'summary').mockResolvedValue({total: 0, usable: 0, newest_at: null});
  vi.spyOn(AnalysisRecordsService, 'list').mockResolvedValue(recordPage());
  vi.spyOn(AnalysisRecordsService, 'summary').mockResolvedValue(recordSummary());
  vi.spyOn(AnalysisRecordsService, 'dailyCounts').mockResolvedValue({days: []});
  vi.spyOn(AnalysisRecordsService, 'askers').mockResolvedValue({items: []});
  vi.spyOn(AnalysisRecordsService, 'detail').mockRejectedValue(new ApiError(404, 'Kayıt bulunamadı.', 'analysis_record_not_found'));
  vi.spyOn(VocabularyService, 'read').mockImplementation(async (list) => (list === 'terms' ? termList([]) : stopList([])));
}

/** The browser's confirmation dialog, answered by the test. */
export function answerConfirm(...answers: boolean[]) {
  const confirm = vi.fn<(text: string) => boolean>(() => (answers.length > 1 ? (answers.shift() as boolean) : answers[0]));
  Object.defineProperty(window, 'confirm', {value: confirm, configurable: true, writable: true});
  // The admin shell's dialog asks through `confirmAction`; the test answers in its place.
  setConfirmHandler((text) => confirm(text));
  return confirm;
}
