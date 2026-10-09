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

/** "850 ms", "2,4 sn", "12 sn", "3 dk 05 sn" (admin.html msText). */
export function formatDuration(milliseconds: number | null | undefined, t: Translate): string {
  const ms = Math.round(milliseconds || 0);
  if (ms < 1000) return t('common.duration.ms', {ms});
  if (ms < 60000)
    return t('common.duration.seconds', {
      seconds: (ms / 1000).toLocaleString(LOCALE, {maximumFractionDigits: ms < 10000 ? 1 : 0}),
    });
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return t('common.duration.minutes', {minutes, seconds: String(seconds).padStart(2, '0')});
}

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

/** Token counts: "950", "12,3 k", "1,2 M" (admin.html kilo). */
export function formatKilo(value: number | null | undefined, t: Translate): string {
  const n = value || 0;
  const short = (scaled: number) => scaled.toLocaleString(LOCALE, {maximumFractionDigits: 1});
  if (n >= 1e6) return t('common.kilo.millions', {value: short(n / 1e6)});
  if (n >= 1e3) return t('common.kilo.thousands', {value: short(n / 1e3)});
  return String(n);
}
