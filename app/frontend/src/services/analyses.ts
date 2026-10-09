import {apiRequest} from '@/lib/apiClient';
import {downloadFile} from '@/lib/download';
import {followEventStream, type FollowOutcome, type StreamEvent} from '@/lib/eventStream';
import type {ActiveAnalysis, AnalysisJob, AnalysisJobWithResult, ServiceStatus} from '@/types/analysis';

const BASE = '/analyses';
const path = (id: string, tail = '') => `${BASE}/${encodeURIComponent(id)}${tail}`;

/** The question flow's calls (data-dictionary/PRDs/004-question-analysis, API contract). */
export const AnalysisService = {
  /** Accept a question; a kept answer completes the job at once (Requirement 4, 14). */
  start(query: string, fresh: boolean): Promise<AnalysisJob> {
    // The page always asks for five suggestions (Decision 20).
    return apiRequest<AnalysisJob>(BASE, {method: 'POST', body: JSON.stringify({query, top: 5, fresh})});
  },
  /** The person's newest queued or running single question, if any (Requirement 19). */
  async active(): Promise<AnalysisJob | null> {
    return (await apiRequest<ActiveAnalysis>(`${BASE}/active`)).analysis;
  },
  /** The job, with its answer once completed. */
  get(id: string, signal?: AbortSignal): Promise<AnalysisJobWithResult> {
    return apiRequest<AnalysisJobWithResult>(path(id), {signal});
  },
  /** Stop the job; a finished job keeps its state (Requirement 11). */
  cancel(id: string): Promise<AnalysisJob> {
    return apiRequest<AnalysisJob>(path(id, '/cancel'), {method: 'POST'});
  },
  /**
   * Follow the live events until the terminal one, reconnecting with `Last-Event-ID`
   * (Requirement 10, 20). Keep-alive comment lines are skipped by the reader.
   */
  follow(id: string, onEvent: (event: StreamEvent) => boolean | void, signal: AbortSignal): Promise<FollowOutcome> {
    return followEventStream(path(id, '/events'), {onEvent, signal});
  },
  /** The Excel report through the shared client; the name comes from the response (Requirement 16, 21). */
  report(id: string): Promise<string> {
    return downloadFile(path(id, '/report'), 'VSA_ask_talep.xlsx');
  },
  /** The dictionary, the model and the shortlist the engine serves with (Requirement 17). */
  status(): Promise<ServiceStatus> {
    return apiRequest<ServiceStatus>('/status');
  },
};
