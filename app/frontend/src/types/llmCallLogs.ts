export type LlmCallPurpose = 'analysis' | 'connection_test' | 'evaluation' | 'dictionary_sync';

export interface LlmCallRow {
  public_id: string;
  purpose: string;
  outcome: string;
  model: string;
  integration_public_id: string | null;
  analysis_public_id: string | null;
  started_at: string;
  wait_ms: number;
  duration_ms: number;
  http_status: number | null;
  requests: number;
  repaired: boolean;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface LlmCallPage {
  rows: LlmCallRow[];
  total: number;
  /** 0 means the log is turned off. */
  retention_days: number;
  /** When the server read the list; deleting with it spares the calls that came later. */
  until: string;
}

export interface LlmCallFiltersToDelete {
  purpose: string;
  outcome: string;
  q: string;
  analysis: string;
}

export interface LlmCallsDeleted {
  deleted_count: number;
  remaining_count: number;
}

export interface LlmCallExchange {
  request: string;
  request_truncated: boolean;
  /** Empty when no response arrived. */
  status: number | null;
  response: string;
  response_truncated: boolean;
  duration_ms: number;
}

export interface LlmCallDetail extends LlmCallRow {
  adaptations: string[];
  exchanges: LlmCallExchange[];
}

export interface LlmCallFilters {
  purpose: string;
  outcome: string;
  q: string;
  /** Only the calls of this analysis (its public id); empty for all. */
  analysis?: string;
  limit: number;
}
