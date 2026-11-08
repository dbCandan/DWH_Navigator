import {apiRequest} from '@/lib/apiClient';
import type {
  DictionarySource,
  DictionarySourceInput,
  DictionarySourceTest,
  DictionaryVersion,
  SyncChange,
  SyncChangeKind,
  SyncPage,
  SyncRunDetail,
  SyncPreview,
  SyncRecordEdit,
  SyncRunSummary,
} from '@/types/dictionarySync';

const BASE = '/dictionary';
const runPath = (id: string) => `${BASE}/sync/runs/${encodeURIComponent(id)}`;

/** The dictionary sync's calls (data-dictionary/PRDs/011-dictionary-sync/plan.md, API sözleşmesi). */
export const DictionarySyncService = {
  source(): Promise<DictionarySource> {
    return apiRequest<DictionarySource>(`${BASE}/source`);
  },
  saveSource(body: DictionarySourceInput): Promise<DictionarySource> {
    return apiRequest<DictionarySource>(`${BASE}/source`, {method: 'PUT', body: JSON.stringify(body)});
  },
  testSource(body: DictionarySourceInput): Promise<DictionarySourceTest> {
    return apiRequest<DictionarySourceTest>(`${BASE}/source/test`, {method: 'POST', body: JSON.stringify(body)});
  },
  /** Starts a run in the background and answers at once with its summary (202). */
  preview(): Promise<SyncPreview> {
    return apiRequest<SyncPreview>(`${BASE}/sync/preview`);
  },
  start(): Promise<SyncRunSummary> {
    return apiRequest<SyncRunSummary>(`${BASE}/sync`, {method: 'POST'});
  },
  runs(page: number, pageSize: number): Promise<SyncPage<SyncRunSummary>> {
    const query = new URLSearchParams({page: String(page), page_size: String(pageSize)});
    return apiRequest<SyncPage<SyncRunSummary>>(`${BASE}/sync/runs?${query.toString()}`);
  },
  run(id: string): Promise<SyncRunDetail> {
    return apiRequest<SyncRunDetail>(runPath(id));
  },
  changes(
    id: string,
    params: {kind?: SyncChangeKind | ''; search?: string; page: number; pageSize: number},
  ): Promise<SyncPage<SyncChange>> {
    const query = new URLSearchParams({page: String(params.page), page_size: String(params.pageSize)});
    if (params.kind) query.set('kind', params.kind);
    if (params.search) query.set('search', params.search);
    return apiRequest<SyncPage<SyncChange>>(`${runPath(id)}/changes?${query.toString()}`);
  },
  approve(id: string): Promise<SyncRunDetail> {
    return apiRequest<SyncRunDetail>(`${runPath(id)}/approve`, {method: 'POST'});
  },
  editRecord(id: string, body: SyncRecordEdit): Promise<SyncRunDetail> {
    return apiRequest<SyncRunDetail>(`${runPath(id)}/records`, {method: 'PATCH', body: JSON.stringify(body)});
  },
  reject(id: string): Promise<SyncRunDetail> {
    return apiRequest<SyncRunDetail>(`${runPath(id)}/reject`, {method: 'POST'});
  },
  applySuggestions(id: string, suggestionIds: string[]): Promise<SyncRunDetail> {
    return apiRequest<SyncRunDetail>(`${runPath(id)}/suggestions/apply`, {
      method: 'POST',
      body: JSON.stringify({suggestion_ids: suggestionIds}),
    });
  },
  async versions(): Promise<DictionaryVersion[]> {
    return (await apiRequest<{items: DictionaryVersion[]}>(`${BASE}/versions`)).items;
  },
  /** A new active version with the chosen one's content, built by a background run (202). */
  restore(id: string): Promise<SyncRunSummary> {
    return apiRequest<SyncRunSummary>(`${BASE}/versions/${encodeURIComponent(id)}/restore`, {method: 'POST'});
  },
};
