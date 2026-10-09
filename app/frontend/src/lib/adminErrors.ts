import {ApiError, isUnreachable} from '@/lib/apiClient';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/**
 * Codes whose `message` the screen shows as the server words it: the dictionary workbook's
 * validation (dictionary-management Requirement 5, 15), the word lists' checks
 * (vocabulary-management Decision 6) and the settings' checks (search-settings Decision 12).
 * Each message is built only from the uploaded file or the sent values.
 */
const SERVER_WORDED = /^(dictionary_workbook_invalid|vocabulary_.+|search_setting_(unknown|invalid))$/;

/** Codes with a fixed text in the catalog (`admin.error.<code>`). */
const CATALOGUED = new Set([
  'search_index_build_failed',
  'search_change_busy',
  'upload_too_large',
  'unsupported_media_type',
  'dictionary_file_empty',
  'dictionary_import_in_progress',
  'dictionary_not_imported',
  'dictionary_table_not_found',
]);

/**
 * The person-facing text of a failed dictionary, word list, settings or index request (rules/31):
 * the server's own sentence for the validation codes above, the catalog text for the other known
 * codes, "Sunucuya ulaşılamadı" for a lost connection and "Beklenmeyen yanıt (HTTP n)" otherwise.
 */
export function adminErrorText(error: unknown, t: Translate): string {
  if (isUnreachable(error)) return t('admin.unreachable.title');
  if (error instanceof ApiError) {
    if (error.code && SERVER_WORDED.test(error.code)) return error.message;
    if (error.code && CATALOGUED.has(error.code)) return t(`admin.error.${error.code}`);
    return t('ai.error.unexpected', {status: error.status});
  }
  return t('ai.error.unexpectedPlain');
}
