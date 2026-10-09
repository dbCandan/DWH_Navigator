import {formatDuration, formatNumber, formatWhen} from '@/lib/format';
import type {Flow, Period, PhaseName, RecordStep, RecordSummary} from '@/types/records';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** The six flows in the order of the "Cevabı yazan" selection (Requirement 2, 16). */
export const FLOWS: readonly Flow[] = ['analyst', 'reused', 'unavailable', 'cancelled', 'failed', 'interrupted'];

/**
 * The flow chip's class: the source's Turkish flow names, which admin.css colours
 * (admin.html flowChip). `interrupted` is new and takes the stopped flow's colour.
 */
export const FLOW_CLASS: Record<Flow, string> = {
  analyst: 'analist',
  reused: 'önbellek',
  unavailable: 'yapılamadı',
  cancelled: 'durduruldu',
  failed: 'hata',
  interrupted: 'kesildi',
};

export const PERIODS: readonly Period[] = ['today', '7d', '30d', 'all'];

/**
 * The six phases in display order with the source's colour class (admin.html PHASES; Requirement
 * 3). The names and notes are catalog messages `records.phase.<phase>` and `.note`.
 */
export const PHASES: readonly {phase: PhaseName; cls: string; note: boolean}[] = [
  {phase: 'queue', cls: 'wait', note: true},
  {phase: 'saved_answer_lookup', cls: 'check', note: true},
  {phase: 'model_check', cls: 'check', note: false},
  {phase: 'rule_hints', cls: 'rules', note: true},
  {phase: 'analyst_pick', cls: 'pick', note: true},
  {phase: 'analyst_write', cls: 'write', note: true},
];

/** A queue wait shorter than this is not shown in a record's phases (admin.html phasesOf). */
const QUEUE_SHOWN_FROM_MS = 1000;

/** A record's phases with time spent, in order; a short queue wait is left out. */
export function shownPhases(phases: Record<string, number>) {
  return PHASES.map((p) => ({...p, ms: phases[p.phase] ?? 0})).filter(
    (p) => p.ms > 0 && (p.phase !== 'queue' || p.ms >= QUEUE_SHOWN_FROM_MS),
  );
}

/**
 * The steps in tree order (Requirement 19; admin.html timeline): every step under its parent,
 * siblings by start and then by sequence number, with their depth.
 */
export function treeOrder(steps: readonly RecordStep[]): [RecordStep, number][] {
  const children = new Map<number | 'root', RecordStep[]>();
  const known = new Set(steps.map((step) => step.seq));
  for (const step of steps) {
    const parent = step.parent !== null && known.has(step.parent) ? step.parent : 'root';
    const list = children.get(parent) ?? [];
    list.push(step);
    children.set(parent, list);
  }
  const ordered: [RecordStep, number][] = [];
  const walk = (parent: number | 'root', depth: number) => {
    const list = [...(children.get(parent) ?? [])].sort((a, b) => a.start_ms - b.start_ms || a.seq - b.seq);
    for (const step of list) {
      ordered.push([step, depth]);
      walk(step.seq, depth + 1);
    }
  };
  walk('root', 0);
  return ordered;
}

/** The summary without its leading verdict word and separator (admin.html detail). */
export const withoutVerdict = (summary: string) => summary.replace(/^(KISMEN VAR|VAR|BULUNAMADI)\s*[.—–-]\s*/, '');

/** The last part of a `DB.Şema.Obje` key. */
export const tableName = (key: string) => key.split('.').pop() ?? key;

/**
 * A failed model call's fixed Turkish text (llm-connection Requirement 13, chat wording): the
 * class from the step's call summary, with the HTTP code where the text names it.
 */
export function callOutcomeText(call: Record<string, unknown> | null | undefined, t: Translate): string {
  const outcome = typeof call?.outcome === 'string' ? call.outcome : '';
  if (!outcome || outcome === 'ok' || !OUTCOMES.has(outcome)) return '';
  const status = typeof call?.http_status === 'number' ? call.http_status : '?';
  return t(`records.outcome.${outcome}`, {status});
}

/**
 * A step's detail as shown: a failed step that names a fixed failure class (the server check
 * stores the class itself) shows its Turkish text, with the check's HTTP code where named.
 */
export function stepDetailText(step: Pick<RecordStep, 'detail' | 'status' | 'check'>, t: Translate): string {
  if (step.status !== 'error' || !OUTCOMES.has(step.detail)) return step.detail;
  const status = typeof step.check?.http_status === 'number' ? step.check.http_status : '?';
  return t(`records.outcome.${step.detail}`, {status});
}

const OUTCOMES = new Set([
  'not_configured',
  'key_unreadable',
  'network_policy_denied',
  'name_unresolved',
  'connect_refused',
  'connect_error',
  'tls_error',
  'timeout',
  'unauthorized',
  'context_exceeded',
  'upstream_status',
  'invalid_response',
  'invalid_json',
  'response_too_large',
  'cancelled',
]);

/** A whole-number field of a step's call summary; 0 when missing. */
export function callNumber(call: Record<string, unknown> | null | undefined, field: string): number {
  const value = call?.[field];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

export interface Kpi {
  k: string;
  v: string;
  s: string;
}

/**
 * The four indicators of a set of records (analysis-records Requirement 15; admin.html
 * Analyses.kpi) from the server's summary; a zero denominator reads "–".
 */
export function recordKpis(summary: RecordSummary, t: Translate): Kpi[] {
  const flows = summary.flows;
  const count = summary.count;
  const reused = flows.reused ?? 0;
  const answered = (flows.analyst ?? 0) + reused;
  const failed = (flows.unavailable ?? 0) + (flows.failed ?? 0) + (flows.interrupted ?? 0);
  const pct = (a: number, b: number) => (b ? t('records.kpi.percent', {value: Math.round((100 * a) / b)}) : t('records.kpi.blank'));
  return [
    {
      k: t('records.kpi.questions'),
      v: formatNumber(count),
      s: count && summary.newest_at ? t('records.kpi.questionsLast', {when: formatWhen(summary.newest_at, t)}) : t('records.kpi.none'),
    },
    {
      k: t('records.kpi.tables'),
      v: pct(summary.with_tables, summary.with_result),
      s: summary.with_result
        ? t('records.kpi.tablesLine', {found: formatNumber(summary.with_tables), answered: formatNumber(summary.with_result)})
        : t('records.kpi.none'),
    },
    {
      k: t('records.kpi.analyst'),
      v: pct(answered, count),
      s: failed
        ? t('records.kpi.analystFailed', {count: formatNumber(failed)})
        : reused
          ? t('records.kpi.analystReused', {count: formatNumber(reused)})
          : t('records.kpi.analystAll'),
    },
    {
      k: t('records.kpi.typical'),
      v: summary.analyst_p50_ms === null ? t('records.kpi.blank') : formatDuration(summary.analyst_p50_ms, t),
      s:
        summary.analyst_p90_ms === null
          ? t('records.kpi.typicalNone')
          : t('records.kpi.typicalP90', {duration: formatDuration(summary.analyst_p90_ms, t)}),
    },
  ];
}
