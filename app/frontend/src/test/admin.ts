import {vi} from 'vitest';
import {DictionaryService} from '@/services/dictionary';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {SavedAnswersService} from '@/services/savedAnswers';
import {SearchSettingsService} from '@/services/searchSettings';
import {VocabularyService} from '@/services/vocabulary';
import type {DictionaryState, DictionaryTable} from '@/types/dictionary';
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

export const termList = (items: TermItem[], revision = 1): VocabularyListState => ({list: 'terms', revision, items});
export const stopList = (items: StopwordItem[], revision = 1): VocabularyListState => ({list: 'stopwords', revision, items});

/** The admin shell's reads answered with an empty, settled installation unless a test says otherwise. */
export function serveAdminDefaults() {
  vi.spyOn(LlmIntegrationService, 'list').mockResolvedValue(llmState());
  vi.spyOn(SearchSettingsService, 'settings').mockResolvedValue(searchSettings());
  vi.spyOn(SearchSettingsService, 'index').mockResolvedValue(indexState({columns: 0, objects: 0, dictionary_version: ''}));
  vi.spyOn(DictionaryService, 'state').mockResolvedValue(EMPTY_DICTIONARY);
  vi.spyOn(DictionaryService, 'tables').mockResolvedValue([]);
  vi.spyOn(SavedAnswersService, 'summary').mockResolvedValue({total: 0, usable: 0, newest_at: null});
  vi.spyOn(VocabularyService, 'read').mockImplementation(async (list) => (list === 'terms' ? termList([]) : stopList([])));
}

/** The browser's confirmation dialog, answered by the test. */
export function answerConfirm(...answers: boolean[]) {
  const confirm = vi.fn(() => (answers.length > 1 ? (answers.shift() as boolean) : answers[0]));
  Object.defineProperty(window, 'confirm', {value: confirm, configurable: true, writable: true});
  return confirm;
}
