import {apiRequest} from '@/lib/apiClient';
import {downloadFile} from '@/lib/download';
import {workbookUpload} from '@/lib/excelUpload';
import type {AnalysisAnswer} from '@/types/analysis';
import type {TermList, TermListPage} from '@/types/termLists';

const BASE = '/term-lists';
const path = (id: string, tail = '') => `${BASE}/${encodeURIComponent(id)}${tail}`;

/** The term list's calls (data-dictionary/PRDs/005-list-search, API contract). */
export const TermListService = {
  /** Upload the workbook as the raw body with its name in `X-Filename` (Requirement 2-4). */
  start(file: File): Promise<TermList> {
    return apiRequest<TermList>(BASE, workbookUpload(file));
  },
  /** The person's kept lists, newest first; the page opening reads the newest (Requirement 15). */
  newest(): Promise<TermListPage> {
    return apiRequest<TermListPage>(`${BASE}?page=1&page_size=1`);
  },
  get(id: string): Promise<TermList> {
    return apiRequest<TermList>(path(id));
  },
  /** An answered term's full answer, the votes applied for the person (Requirement 12). */
  item(id: string, position: number): Promise<AnalysisAnswer> {
    return apiRequest<AnalysisAnswer>(path(id, `/items/${position}`));
  },
  cancel(id: string): Promise<TermList> {
    return apiRequest<TermList>(path(id, '/cancel'), {method: 'POST'});
  },
  resume(id: string): Promise<TermList> {
    return apiRequest<TermList>(path(id, '/resume'), {method: 'POST'});
  },
  /** The list report so far or in full, through the shared client (Requirement 13). */
  report(id: string): Promise<string> {
    return downloadFile(path(id, '/report'), 'VSA_liste.xlsx');
  },
  /** A term's single-question report from its kept answer (Requirement 12). */
  itemReport(id: string, position: number): Promise<string> {
    return downloadFile(path(id, `/items/${position}/report`), 'VSA_ask_talep.xlsx');
  },
};
