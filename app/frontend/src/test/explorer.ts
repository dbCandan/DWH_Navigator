import {vi} from 'vitest';
import type {StreamEvent} from '@/lib/eventStream';
import {AnalysisService} from '@/services/analyses';
import type {
  AnalysisAnswer,
  AnalysisJob,
  AnalysisStreamEvent,
  AnswerObject,
  ServiceStatus,
} from '@/types/analysis';

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

/** The main screen's reads answered with a ready installation and no running question. */
export function serveExplorerDefaults() {
  vi.spyOn(AnalysisService, 'status').mockResolvedValue(serviceStatus());
  vi.spyOn(AnalysisService, 'active').mockResolvedValue(null);
}
