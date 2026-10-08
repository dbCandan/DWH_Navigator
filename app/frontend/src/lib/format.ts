/** Turkish number, date and time formatting, as the source screens wrote them. */
const LOCALE = 'tr-TR';

export function formatNumber(value: number | null | undefined): string {
  return Number(value || 0).toLocaleString(LOCALE);
}

/** "8 Eki 2026 14:05" (admin.html fmtAt). */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(LOCALE, {dateStyle: 'medium', timeStyle: 'short'});
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** "bugün 14:05", else "08.10 14:05" (with the year when it is not this year); admin.html when(). */
export function formatWhen(iso: string, t: Translate, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const time = date.toLocaleTimeString(LOCALE, {hour: '2-digit', minute: '2-digit'});
  if (now.toDateString() === date.toDateString()) return t('common.when.today', {time});
  const day = date.toLocaleDateString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  });
  return t('common.when.date', {date: day, time});
}
