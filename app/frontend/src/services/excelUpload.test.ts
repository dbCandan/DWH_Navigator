import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, writeSession} from '@/lib/authStorage';
import {DictionaryService} from './dictionary';
import {VocabularyService} from './vocabulary';
import type {AuthenticatedUser} from '@/types/auth';

describe('workbook uploads (dictionary-management Requirement 2; vocabulary-management Requirement 7)', () => {
  beforeEach(() => writeSession('token', {username: 'u', tenant_id: 't'} as AuthenticatedUser));
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('sends the workbook as the body with its media type and percent-encoded name', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', {status: 201}));
    const file = new File(['PK'], 'Sözlük 2026.xlsx');
    await DictionaryService.importWorkbook(file);
    await VocabularyService.importWorkbook('stopwords', file);
    const [[dictionaryUrl, dictionaryInit], [listUrl, listInit]] = fetchMock.mock.calls;
    expect(String(dictionaryUrl)).toBe('/api/dwhnavigator/v1/dictionary/imports');
    expect(String(listUrl)).toBe('/api/dwhnavigator/v1/vocabulary/stopwords/import');
    for (const init of [dictionaryInit, listInit]) {
      const headers = new Headers(init?.headers);
      expect(init?.method).toBe('POST');
      expect(init?.body).toBe(file);
      expect(headers.get('Content-Type')).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      expect(headers.get('X-Filename')).toBe('S%C3%B6zl%C3%BCk%202026.xlsx');
      expect(headers.get('Authorization')).toBe('Bearer token');
    }
  });

  it('reads every page of the table list', async () => {
    vi.mocked(DictionaryService.tables).mockRestore();
    const page = (items: number, total: number) =>
      new Response(JSON.stringify({items: Array.from({length: items}, (_, at) => ({key: `k${at}`})), total, page: 1, page_size: 1000}));
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(page(1000, 1500)).mockResolvedValueOnce(page(500, 1500));
    expect(await DictionaryService.tables()).toHaveLength(1500);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      '/api/dwhnavigator/v1/dictionary/tables?page=1&page_size=1000',
      '/api/dwhnavigator/v1/dictionary/tables?page=2&page_size=1000',
    ]);
  });
});
