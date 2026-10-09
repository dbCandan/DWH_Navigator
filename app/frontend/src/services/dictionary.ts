import {apiRequest} from '@/lib/apiClient';
import {downloadFile} from '@/lib/download';
import {workbookUpload} from '@/lib/excelUpload';
import type {
  DictionaryImported,
  DictionaryState,
  DictionaryTable,
  DictionaryTableRecords,
  DictionaryTablesPage,
} from '@/types/dictionary';

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
  /** One table's Objeler record and Kolonlar records as imported. */
  table(key: string): Promise<DictionaryTableRecords> {
    return apiRequest<DictionaryTableRecords>(`${BASE}/tables/${encodeURIComponent(key)}`);
  },
  /** A new version from the workbook; `changed: false` when the content is the active one's. */
  importWorkbook(file: File): Promise<DictionaryImported> {
    return apiRequest<DictionaryImported>(`${BASE}/imports`, workbookUpload(file));
  },
  /** The active version as the template's workbook, saved under the server's name. */
  exportWorkbook(): Promise<string> {
    return downloadFile(`${BASE}/export`, 'VeriSozlugu.xlsx');
  },
  template(): Promise<string> {
    return downloadFile(`${BASE}/template`, 'VeriSozlugu_sablon.xlsx');
  },
};
