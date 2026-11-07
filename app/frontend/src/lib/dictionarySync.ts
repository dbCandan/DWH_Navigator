import type {SyncRunStatus, SyncRunSummary} from '@/types/dictionarySync';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** The `pill` class of a run's result. */
export function runPill(status: SyncRunStatus): string {
  if (status === 'completed') return 'pill ok';
  if (status === 'running') return 'pill acc';
  if (status === 'pending_approval' || status === 'interrupted') return 'pill warn';
  if (status === 'failed') return 'pill bad';
  return 'pill';
}

/** The failure classes a run can close with (plan.md, Hata kodları); others read as the generic class. */
const FAILURE_CLASSES = new Set([
  'dictionary_source_not_configured',
  'dictionary_source_unavailable',
  'dictionary_source_invalid',
  'dictionary_target_unavailable',
]);

/** The class of a failed or cut run, never the raw code; empty for any other run. */
export function runFailureText(run: Pick<SyncRunSummary, 'status' | 'error_code'>, t: Translate): string {
  if (run.status === 'interrupted') return t('dictionary.report.interrupted');
  if (run.status !== 'failed') return '';
  return FAILURE_CLASSES.has(run.error_code) ? t(`admin.error.${run.error_code}`) : t('dictionary.report.failedOther');
}

/** The share of the work in whole percent, or null while the total is not known. */
export function runPercent(run: Pick<SyncRunSummary, 'progress_done' | 'progress_total'>): number | null {
  if (run.progress_total <= 0) return null;
  return Math.min(100, Math.round((run.progress_done / run.progress_total) * 100));
}
