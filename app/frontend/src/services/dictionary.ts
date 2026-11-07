import {apiRequest} from '@/lib/apiClient';
import {downloadFile} from '@/lib/download';
import type {DictionaryState, DictionaryTable, DictionaryTableRecords, DictionaryTablesPage} from '@/types/dictionary';

const BASE = '/dictionary';
const PAGE_SIZE = 1000;

/** The Sözlük page's calls (data-dictionary/PRDs/001-dictionary-management, API contract). */
export const DictionaryService = {
  /** The active and previous version and the version the serving index was built from. */
  state(): Promise<DictionaryState> {
    return apiRequest<DictionaryState>(BASE);
  },
  /** Every table of the active version, page by page (Requirement 18). */
  async tables(): Promise<DictionaryTable[]> {
    const items: DictionaryTable[] = [];
    for (let page = 1; ; page += 1) {
      const answer = await apiRequest<DictionaryTablesPage>(`${BASE}/tables?page=${page}&page_size=${PAGE_SIZE}`);
      items.push(...answer.items);
      if (!answer.items.length || items.length >= answer.total) return items;
    }
  },
  /** One table's Objeler record and Kolonlar records. */
  table(key: string): Promise<DictionaryTableRecords> {
    return apiRequest<DictionaryTableRecords>(`${BASE}/tables/${encodeURIComponent(key)}`);
  },
  /** The active version as a workbook, saved under the server's name. */
  exportWorkbook(): Promise<string> {
    return downloadFile(`${BASE}/export`, 'VeriSozlugu.xlsx');
  },
};
