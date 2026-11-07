import {describe, expect, it} from 'vitest';
import adminCss from '@/components/admin/admin.css?raw';
import {message} from '@/test/render';
import type {RecordStep} from '@/types/records';
import {callOutcomeText, FLOW_CLASS, shownPhases, stepDetailText, treeOrder, withoutVerdict} from './analysisRecords';

const t = (key: string, values?: Record<string, string | number>) => message(key, values);

const step = (seq: number, parent: number | null, start: number, overrides: Partial<RecordStep> = {}): RecordStep => ({
  seq,
  parent,
  name: 'adım ' + seq,
  kind: 'step',
  key: null,
  start_ms: start,
  ms: 10,
  status: 'ok',
  detail: '',
  ...overrides,
});

describe('analysis record helpers (analysis-records Requirement 3, 18, 19)', () => {
  it('orders steps as a tree: children under their parent, siblings by start then sequence', () => {
    const steps = [step(3, 0, 50), step(0, null, 0), step(1, 0, 50), step(2, 1, 60), step(4, null, 40)];
    expect(treeOrder(steps).map(([s, depth]) => [s.seq, depth])).toEqual([
      [0, 0],
      [1, 1],
      [2, 2],
      [3, 1],
      [4, 0],
    ]);
  });

  it('keeps the phases with time in order and drops a queue wait under one second', () => {
    const phases = {queue: 900, saved_answer_lookup: 0, model_check: 120, rule_hints: 30, analyst_pick: 4000, analyst_write: 9000};
    expect(shownPhases(phases).map((p) => [p.phase, p.cls])).toEqual([
      ['model_check', 'check'],
      ['rule_hints', 'rules'],
      ['analyst_pick', 'pick'],
      ['analyst_write', 'write'],
    ]);
    expect(shownPhases({...phases, queue: 1500})[0]).toMatchObject({phase: 'queue', cls: 'wait', ms: 1500});
  });

  it('names a failed model call by its class and HTTP code, and nothing for a successful one', () => {
    expect(callOutcomeText({outcome: 'timeout'}, t)).toBe(message('records.outcome.timeout'));
    expect(callOutcomeText({outcome: 'unauthorized', http_status: 401}, t)).toBe(
      'Sunucu HTTP 401 döndürdü (API anahtarı eksik veya geçersiz)',
    );
    expect(callOutcomeText({outcome: 'output_truncated'}, t)).toBe('model cevabı uzunluk sınırında kesildi');
    expect(callOutcomeText({outcome: 'ok'}, t)).toBe('');
    expect(callOutcomeText(null, t)).toBe('');
  });

  it('shows a failed server check by the Turkish text of its class, other details as written', () => {
    expect(stepDetailText(step(0, null, 0, {status: 'error', detail: 'connect_error'}), t)).toBe(
      message('records.outcome.connect_error'),
    );
    expect(stepDetailText(step(0, null, 0, {status: 'error', detail: 'upstream_status', check: {http_status: 502}}), t)).toBe(
      'Sunucu HTTP 502 döndürdü',
    );
    expect(stepDetailText(step(0, null, 0, {detail: '14 aday, 3 benzer tablo'}), t)).toBe('14 aday, 3 benzer tablo');
  });

  it('drops the leading verdict word of a summary', () => {
    expect(withoutVerdict('KISMEN VAR — iki tablo yakın.')).toBe('iki tablo yakın.');
    expect(withoutVerdict('VAR. Tablo bulundu.')).toBe('Tablo bulundu.');
    expect(withoutVerdict('Tablo yok.')).toBe('Tablo yok.');
  });
});

describe('the interrupted flow chip (analysis-records Requirement 2)', () => {
  it('has the stopped flow\'s colour, the source\'s "durduruldu" chip', () => {
    expect(FLOW_CLASS.interrupted).toBe('kesildi');
    const rule = /([^{}]*\.flow\.kesildi[^{}]*)\{([^}]*)\}/.exec(adminCss);
    expect(rule?.[1]).toContain('.flow.durduruldu');
    expect(rule?.[2].trim()).toBe('color: var(--muted);');
  });
});
