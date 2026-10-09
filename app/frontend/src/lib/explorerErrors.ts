import {ApiError, isUnreachable} from '@/lib/apiClient';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/**
 * Codes whose `message` the main screen shows as the server words it: the term list's reading
 * rules name the row, the column or the count of the uploaded file, and the running list's
 * message says whose list runs (list-search Requirement 3, 4, 9). Each message is built only from
 * the uploaded file or the person's own list.
 */
const SERVER_WORDED = new Set([
  'term_list_not_xlsx',
  'term_list_too_large_unpacked',
  'term_list_too_many_rows',
  'term_list_layout_invalid',
  'term_list_term_too_long',
  'term_list_too_many_terms',
  'term_list_running',
  'term_list_nothing_to_resume',
]);

/** Codes with a fixed text in the catalog (`explorer.error.<code>`). */
const CATALOGUED = new Set([
  'table_not_found',
  'term_list_not_found',
  'term_list_item_not_answered',
  'vote_table_unknown',
  'search_index_not_ready',
  'analysis_unavailable',
  'upload_too_large',
  'unsupported_media_type',
]);

/**
 * The text of a failed table file, vote or term list request on the main screen (rules/31): the
 * server's sentence for the codes above, the catalog text for the other known codes, "Sunucuya
 * ulaşılamadı" for a lost connection and "Beklenmeyen yanıt" otherwise.
 */
export function explorerErrorText(error: unknown, t: Translate): string {
  if (isUnreachable(error) || !(error instanceof ApiError)) return t('explorer.ask.error.unreachable');
  if (error.code && SERVER_WORDED.has(error.code)) return error.message;
  if (error.code && CATALOGUED.has(error.code)) return t(`explorer.error.${error.code}`);
  return t('explorer.ask.error.unexpected');
}
