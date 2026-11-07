import {apiRequest} from '@/lib/apiClient';
import type {LlmCallDetail, LlmCallFilters, LlmCallPage} from '@/types/llmCallLogs';

const BASE = '/llm-call-logs';

/** The LLM log page's calls. */
export const LlmCallLogService = {
  list({purpose, outcome, q, limit}: LlmCallFilters): Promise<LlmCallPage> {
    const query = new URLSearchParams({limit: String(limit)});
    if (purpose) query.set('purpose', purpose);
    if (outcome) query.set('outcome', outcome);
    if (q) query.set('q', q);
    return apiRequest<LlmCallPage>(`${BASE}?${query}`);
  },
  read(publicId: string): Promise<LlmCallDetail> {
    return apiRequest<LlmCallDetail>(`${BASE}/${encodeURIComponent(publicId)}`);
  },
};
