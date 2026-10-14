import {visitorRequest} from '@/lib/apiClient';
import type {Galaxy, TableDetail, TableSearchResult} from '@/types/explorer';

/** The main screen's map, table search and table file (dictionary-explorer API contract). */
export const ExplorerService = {
  /** Every table of the serving index with its group and column count (Requirement 3). */
  galaxy(): Promise<Galaxy> {
    return visitorRequest<Galaxy>('/explorer/galaxy');
  },
  /** The model-free table search; the text travels in the body, never in the address (Decision 9). */
  search(query: string, signal?: AbortSignal): Promise<TableSearchResult> {
    return visitorRequest<TableSearchResult>('/explorer/table-searches', {
      method: 'POST',
      body: JSON.stringify({query}),
      signal,
    });
  },
  /** A table's columns and join keys; the key is percent-encoded (Requirement 11). */
  table(key: string): Promise<TableDetail> {
    return visitorRequest<TableDetail>(`/explorer/tables/${encodeURIComponent(key)}`);
  },
};
