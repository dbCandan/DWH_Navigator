import {apiRequest} from '@/lib/apiClient';
import type {
  LlmCallDetail,
  LlmCallFilters,
  LlmCallFiltersToDelete,
  LlmCallPage,
  LlmCallsDeleted,
} from '@/types/llmCallLogs';

const BASE = '/llm-call-logs';

/** The LLM log page's calls. */
export const LlmCallLogService = {
  list({purpose, outcome, q, analysis, limit}: LlmCallFilters): Promise<LlmCallPage> {
    const query = new URLSearchParams({limit: String(limit)});
    if (purpose) query.set('purpose', purpose);
    if (outcome) query.set('outcome', outcome);
    if (q) query.set('q', q);
    if (analysis) query.set('analysis', analysis);
    return apiRequest<LlmCallPage>(`${BASE}?${query}`);
  },
  read(publicId: string): Promise<LlmCallDetail> {
    return apiRequest<LlmCallDetail>(`${BASE}/${encodeURIComponent(publicId)}`);
  },
  /** Deletes for good the calls before `until`: all of them, or those matching the filters. */
  remove(until: string, scope: {all: true} | {filters: LlmCallFiltersToDelete}): Promise<LlmCallsDeleted> {
    const query = new URLSearchParams({until});
    if ('all' in scope) query.set('all', 'true');
    else
      for (const [key, value] of Object.entries(scope.filters)) {
        if (value) query.set(key, value);
      }
    return apiRequest<LlmCallsDeleted>(`${BASE}?${query}`, {method: 'DELETE'});
  },
};
