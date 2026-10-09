import type {TermList} from '@/types/termLists';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** "{n} sn", or "{n} dk" from a minute on (list-search Requirement 17; index.html Bulk.dur). */
export function listDuration(ms: number, t: Translate): string {
  return ms >= 60000
    ? t('list.minutes', {count: Math.round(ms / 60000)})
    : t('list.seconds', {count: Math.max(1, Math.round(ms / 1000))});
}

/** The answered terms the analyst could not write ("Analiz yapılamadı"). */
export const unavailableCount = (list: TermList): number =>
  list.items.filter((i) => i.state === 'answered' && i.flow === 'unavailable').length;
