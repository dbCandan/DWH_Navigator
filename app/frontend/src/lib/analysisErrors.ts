import {ApiError, isUnreachable} from '@/lib/apiClient';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Error codes of the question flow with a fixed Turkish text (`explorer.ask.error.<code>`). */
const KNOWN = new Set([
  'query_empty',
  'query_too_long',
  'query_invalid_characters',
  'request_too_large',
  'rate_limited',
  'analysis_queue_full',
  'analysis_unavailable',
  'search_index_not_ready',
  'analysis_failed',
  'analysis_not_found',
  'too_many_streams',
]);

/** The text of an error code; the server's own wording is never shown (Requirement 19). */
export function askCodeText(code: string | undefined, t: Translate): string {
  return code && KNOWN.has(code) ? t(`explorer.ask.error.${code}`) : t('explorer.ask.error.unexpected');
}

/** The text after "Analiz başarısız: " for a failed request of the question flow. */
export function askErrorText(error: unknown, t: Translate): string {
  if (isUnreachable(error)) return t('explorer.ask.error.unreachable');
  return askCodeText(error instanceof ApiError ? error.code : undefined, t);
}
