import {apiRequest} from '@/lib/apiClient';
import {downloadFile} from '@/lib/download';
import {workbookUpload} from '@/lib/excelUpload';
import type {VocabularyItems, VocabularyListName, VocabularyListSaved, VocabularyListState} from '@/types/vocabulary';

const path = (list: VocabularyListName) => `/vocabulary/${list}`;
const FALLBACK_NAME: Record<VocabularyListName, string> = {terms: 'TerimSozlugu.xlsx', stopwords: 'DurakKelimeler.xlsx'};

/** The Kelimeler page's calls (data-dictionary/PRDs/002-vocabulary-management, API contract). */
export const VocabularyService = {
  read(list: VocabularyListName): Promise<VocabularyListState> {
    return apiRequest<VocabularyListState>(path(list));
  },
  /** The whole list; the index is rebuilt with it, or nothing is written (Requirement 5). */
  save<L extends VocabularyListName>(list: L, items: VocabularyItems[L]): Promise<VocabularyListSaved> {
    return apiRequest<VocabularyListSaved>(path(list), {method: 'PUT', body: JSON.stringify({items})});
  },
  /** A workbook's sheet replaces the list through the same path as a save (Requirement 7-8). */
  importWorkbook(list: VocabularyListName, file: File): Promise<VocabularyListSaved> {
    return apiRequest<VocabularyListSaved>(`${path(list)}/import`, workbookUpload(file));
  },
  /** The saved list as a one-sheet workbook (Requirement 6). */
  exportWorkbook(list: VocabularyListName): Promise<string> {
    return downloadFile(`${path(list)}/export`, FALLBACK_NAME[list]);
  },
};
