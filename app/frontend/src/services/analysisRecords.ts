import {apiRequest} from '@/lib/apiClient';
import type {
  Askers,
  DailyCounts,
  RecordDetail,
  RecordFilters,
  RecordPage,
  RecordsDeleted,
  RecordSummary,
} from '@/types/records';

/** The page size of the Analizler list (Requirement 6, 16). */
export const RECORD_PAGE_SIZE = 150;

/** The query string of the filters; empty filters are left out (`period` always goes). */
function query(filters: RecordFilters, extra: Record<string, string | number | undefined> = {}): string {
  const params = new URLSearchParams({period: filters.period});
  if (filters.flow) params.set('flow', filters.flow);
  if (filters.asked_by) params.set('asked_by', filters.asked_by);
  if (filters.q) params.set('q', filters.q);
  for (const [key, value] of Object.entries(extra)) if (value !== undefined) params.set(key, String(value));
  return '?' + params.toString();
}

/**
 * The finished analysis records of the admin screen (data-dictionary/PRDs/008-analysis-records,
 * API sözleşmesi): the list, its summary, the daily counts, the askers, one record and the
 * deletion. Records are addressed by their `public_id` only.
 */
export const AnalysisRecordsService = {
  /** A page of the matching records, newest first, computed at `until` (Requirement 6). */
  list(filters: RecordFilters, page = 1, until?: string, pageSize = RECORD_PAGE_SIZE): Promise<RecordPage> {
    return apiRequest<RecordPage>('/analysis-records' + query(filters, {until, page, page_size: pageSize}));
  },
  /** Counts, durations, phases, model use and askers of the matching records (Requirement 7). */
  summary(filters: RecordFilters, until?: string): Promise<RecordSummary> {
    return apiRequest<RecordSummary>('/analysis-records/summary' + query(filters, {until}));
  },
  /** Records with and without suggested tables per day, oldest first (Requirement 8). */
  dailyCounts(days = 14): Promise<DailyCounts> {
    return apiRequest<DailyCounts>(`/analysis-records/daily-counts?days=${days}`);
  },
  /** Everyone with a finished record, by display name (Requirement 9). */
  askers(): Promise<Askers> {
    return apiRequest<Askers>('/analysis-records/askers');
  },
  /** One record with its phases and steps (Requirement 10). */
  detail(publicId: string): Promise<RecordDetail> {
    return apiRequest<RecordDetail>('/analysis-records/' + encodeURIComponent(publicId));
  },
  /** Delete the matching records accepted before `until`, or every one of them (Requirement 11). */
  remove(until: string, scope: {all: true} | {filters: RecordFilters}): Promise<RecordsDeleted> {
    const path =
      'all' in scope
        ? '/analysis-records?' + new URLSearchParams({until, all: 'true'}).toString()
        : '/analysis-records' + query(scope.filters, {until});
    return apiRequest<RecordsDeleted>(path, {method: 'DELETE'});
  },
};
