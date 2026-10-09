import {describe, expect, it} from 'vitest';
import messages from '@/locales/tr.json';
import {ApiError} from './apiClient';
import {adminErrorText} from './adminErrors';

const catalog = messages as Record<string, string>;
const t = (key: string, values: Record<string, string | number> = {}) =>
  (catalog[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(values[name]));

describe('admin error texts (rules/31)', () => {
  it('shows the server sentence only for the validation codes built from the sent content', () => {
    for (const code of ['dictionary_workbook_invalid', 'vocabulary_term_duplicate', 'search_setting_invalid', 'search_setting_unknown'])
      expect(adminErrorText(new ApiError(422, 'sunucu cümlesi', code), t)).toBe('sunucu cümlesi');
  });

  it('uses a catalog text for every other known code and never the raw message', () => {
    for (const code of [
      'search_index_build_failed',
      'search_change_busy',
      'upload_too_large',
      'unsupported_media_type',
      'dictionary_file_empty',
      'dictionary_import_in_progress',
      'dictionary_not_imported',
      'dictionary_table_not_found',
    ]) {
      const text = adminErrorText(new ApiError(500, 'iç ayrıntı', code), t);
      expect(text).toBe(catalog[`admin.error.${code}`]);
    }
    expect(adminErrorText(new ApiError(500, 'iç ayrıntı'), t)).toBe('Beklenmeyen yanıt (HTTP 500)');
    expect(adminErrorText(new TypeError('Failed to fetch'), t)).toBe(catalog['admin.unreachable.title']);
  });
});
