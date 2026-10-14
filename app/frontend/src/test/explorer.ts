import {vi} from 'vitest';
import type {StreamEvent} from '@/lib/eventStream';
import {AnalysisService} from '@/services/analyses';
import {ExplorerService} from '@/services/explorer';
import {TermListService} from '@/services/termLists';
import type {
  AnalysisAnswer,
  AnalysisJob,
  AnalysisStreamEvent,
  AnswerObject,
  ServiceStatus,
} from '@/types/analysis';
import type {GalaxyTable, TableColumn, TableDetail} from '@/types/explorer';
import type {Tally} from '@/types/feedback';
import type {TermList, TermRow} from '@/types/termLists';

/*
 * Synthetic fixtures of the question flow (no real dictionary): a status answer, job envelopes,
 * an analyst answer and live events.
 */

export const ANALYSIS_ID = '11111111-1111-4111-8111-111111111111';

export const serviceStatus = (overrides: Partial<ServiceStatus> = {}): ServiceStatus => ({
  columns: 11136,
  objects: 390,
  dictionary_version: 'abcdef12-11136',
  llm: 'yerel/fake-analyst',
  llm_state: {state: 'ok', model: 'yerel/fake-analyst', code: null, reason: ''},
  shortlist: 14,
  ...overrides,
});

export const job = (overrides: Partial<AnalysisJob> = {}): AnalysisJob => ({
  analysis_id: ANALYSIS_ID,
  state: 'queued',
  origin: 'question',
  query: 'kart limit doluluk oranı',
  fresh: false,
  ahead: 0,
  step: null,
  flow: null,
  error: null,
  created_at: '2026-10-09T08:00:00Z',
  started_at: null,
  finished_at: null,
  ...overrides,
});

export const answerObject = (rank: number, overrides: Partial<AnswerObject> = {}): AnswerObject => ({
  rank,
  key: `DWH.Kart.vCardLimit${rank}`,
  database: 'DWH',
  schema: 'Kart',
  name: `vCardLimit${rank}`,
  groups: ['Kartlar'],
  score: 0.9 - rank * 0.1,
  level: rank === 1 ? 'Yüksek' : 'Orta',
  llm: 0.85,
  components: {best_column: 0.8, coverage: 0.5, time: 1, granularity: 0, topic: 0.6},
  covered: ['limit', 'doluluk'],
  missing: rank === 1 ? [] : ['oran'],
  long_format: rank === 2 ? ['doluluk'] : [],
  dimension: 'Tip',
  reason: `CardLimitAmount kolonu limiti verir; DWH.Kart.vCardLimit${rank} günlük güncellenir.`,
  caveat: rank === 1 ? ['Kapanmış kartlar da dahil.'] : [],
  usage: 'CardLimitAmount ile UsedAmount oranlanır.',
  covers: 'limit ve kullanım',
  columns: Array.from({length: 8}, (_, i) => ({
    key: `DWH.Kart.vCardLimit${rank}.Column${i}`,
    column: i === 0 ? 'CardLimitAmount' : `Column${i}`,
    object: `DWH.Kart.vCardLimit${rank}`,
    description: `Kolon ${i} açıklaması`,
    synonyms: i === 0 ? ['limit tutarı'] : [],
    pii: i === 1,
    group: null,
    role: i === 0 ? 'eşleşme' : i === 1 ? 'yapısal' : '',
    signals: i === 0 ? ['ad eşleşmesi'] : [],
    caveats: i === 0 ? ['boş olabilir'] : [],
  })),
  ...overrides,
});

export const answer = (overrides: Partial<AnalysisAnswer> = {}): AnalysisAnswer => ({
  query: 'kart limit doluluk oranı',
  verdict: 'KISMEN VAR',
  summary:
    'KISMEN VAR — Kart limit doluluğu vCardLimit1 tablosunda hesaplanabilir ve günlük olarak tutulur. Oran hazır bir kolon değildir.',
  objects: [answerObject(1), answerObject(2)],
  near: [],
  notes: [{scope: 'Uyarı', title: 'Kapsam notu', text: 'vCardLimit2 yalnız aktif kartları tutar.'}],
  concepts: ['terim:limit', 'ölçü:doluluk', 'zaman:günlük'],
  expansion: ['kredi limiti', 'limit tutarı'],
  method: ['Analist iki adımda okudu.'],
  elapsed_ms: 48200,
  dictionary_version: 'abcdef12-11136',
  llm_model: 'yerel/fake-analyst',
  analyst: true,
  fallback: '',
  interpretation: 'Kart başına limit kullanım oranı isteniyor.',
  design: ['vCardLimit1 ile başlayın.', 'UsedAmount / CardLimitAmount oranını alın.'],
  attention: ['Kapanmış kartları ayıklayın.'],
  reused: null,
  missing: ['oran'],
  ...overrides,
});

/** A live event as the stream reader hands it over. */
export const event = (data: AnalysisStreamEvent, id = 1): StreamEvent => ({id: String(id), event: 'message', data: JSON.stringify(data)});

/**
 * Serve `follow` from a script: each call (a connection) delivers its events in order and stops
 * at the terminal one; the returned `connect` lets a test push later events by hand.
 */
export function serveEvents(...events: AnalysisStreamEvent[]) {
  return vi.spyOn(AnalysisService, 'follow').mockImplementation(async (_id, onEvent) => {
    let i = 0;
    for (const data of events) if (onEvent(event(data, ++i)) === true) return 'completed';
    return 'completed';
  });
}

/**
 * A small synthetic galaxy: two clusters, a table without a group ("Diğer") and `vCampaign` in two
 * schemas (dictionary-explorer test strategy).
 */
export const GALAXY: GalaxyTable[] = [
  {key: 'DWH.Kart.vCardLimit1', name: 'vCardLimit1', schema: 'DWH.Kart', group: 'Kartlar', columns: 8},
  {key: 'DWH.Kart.vCardLimit2', name: 'vCardLimit2', schema: 'DWH.Kart', group: 'Kartlar', columns: 8},
  {key: 'DWH.Kart.vCardStatistic', name: 'vCardStatistic', schema: 'DWH.Kart', group: 'Kartlar', columns: 33},
  {key: 'DWH.Kart.vCampaign', name: 'vCampaign', schema: 'DWH.Kart', group: 'Kartlar', columns: 4},
  {key: 'DWH.Musteri.vCampaign', name: 'vCampaign', schema: 'DWH.Musteri', group: 'Müşteri', columns: 5},
  {key: 'DWH.Musteri.vCustomerInfo', name: 'vCustomerInfo', schema: 'DWH.Musteri', group: 'Müşteri', columns: 21},
  {key: 'DWH.Ortak.vTakvim', name: 'vTakvim', schema: 'DWH.Ortak', group: 'Diğer', columns: 3},
];

export const column = (name: string, overrides: Partial<TableColumn> = {}): TableColumn => ({
  key: `DWH.Kart.vCardLimit1.${name}`,
  column: name,
  object: 'DWH.Kart.vCardLimit1',
  description: `${name} açıklaması`,
  synonyms: [],
  pii: false,
  group: 'Kartlar',
  ...overrides,
});

export const tableDetail = (overrides: Partial<TableDetail> = {}): TableDetail => ({
  key: 'DWH.Kart.vCardLimit1',
  name: 'vCardLimit1',
  schema: 'DWH.Kart',
  groups: ['Kartlar'],
  columns: [
    column('CustomerPartyId', {description: 'Müşteri anahtarı'}),
    column('CardLimitAmount', {description: 'Kartın İŞLEM limiti', synonyms: ['limit tutarı', 'kredi limiti']}),
    column('CustomerName', {description: '', pii: true}),
    column('DataDate', {description: 'x'.repeat(150)}),
  ],
  join_keys: ['CustomerPartyId', 'DataDate'],
  ...overrides,
});

export const tally = (overrides: Partial<Tally> = {}): Tally => ({
  up: 0,
  down: 0,
  support: 0,
  status: '',
  reasons: [],
  ...overrides,
});

export const termRow = (position: number, overrides: Partial<TermRow> = {}): TermRow => ({
  position,
  term: `terim ${position}`,
  state: 'queued',
  verdict: '',
  summary: '',
  missing: [],
  best: null,
  flow: null,
  elapsed_ms: 0,
  ...overrides,
});

export const LIST_ID = '22222222-2222-4222-8222-222222222222';

export const termList = (overrides: Partial<TermList> = {}): TermList => ({
  id: LIST_ID,
  name: 'terimler.xlsx',
  owner: {public_id: '00000000-0000-4000-8000-000000000001', display_name: 'Ayşe Yılmaz'},
  header: 'Terim',
  notes: [],
  status: 'running',
  stop_requested: false,
  total: 3,
  done: 1,
  elapsed_ms: 4000,
  eta_ms: 8000,
  created_at: '2026-10-09T08:00:00Z',
  finished_at: null,
  dictionary_version: 'abcdef12-11136',
  items: [
    termRow(1, {
      state: 'answered',
      verdict: 'VAR',
      flow: 'analyst',
      summary: 'Bulundu',
      best: {key: 'DWH.Kart.vCardLimit1', name: 'vCardLimit1', score: 0.82, level: 'Yüksek'},
      elapsed_ms: 3000,
    }),
    termRow(2, {state: 'running'}),
    termRow(3),
  ],
  ...overrides,
});

/** The main screen's reads answered with a ready installation and no running question. */
export function serveExplorerDefaults() {
  vi.spyOn(AnalysisService, 'status').mockResolvedValue(serviceStatus());
  vi.spyOn(ExplorerService, 'galaxy').mockResolvedValue({items: GALAXY, total: GALAXY.length});
  vi.spyOn(ExplorerService, 'search').mockResolvedValue({query: '', items: [], counts: {}, concepts: [], elapsed_ms: 1});
  vi.spyOn(ExplorerService, 'table').mockResolvedValue(tableDetail());
  vi.spyOn(TermListService, 'newest').mockResolvedValue({items: [], page: 1, page_size: 1, total: 0});
}
