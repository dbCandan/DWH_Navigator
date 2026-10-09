import {apiRequest} from '@/lib/apiClient';
import type {
  LlmIntegrationCreate,
  LlmIntegrationCreated,
  LlmIntegrationItem,
  LlmIntegrationsState,
  LlmIntegrationUpdate,
  LlmIntegrationUpdated,
  LlmInventory,
  LlmModelsRequest,
  LlmModelsResult,
  LlmTestRequest,
  LlmTestResult,
} from '@/types/llm';

const BASE = '/llm-integrations';
const one = (item: Pick<LlmIntegrationItem, 'public_id'>) => `${BASE}/${encodeURIComponent(item.public_id)}`;
const json = (method: string, body: unknown): RequestInit => ({method, body: JSON.stringify(body)});

/** The AI page's calls (data-dictionary/PRDs/003-llm-connection, API contract). */
export const LlmIntegrationService = {
  /** Integrations, the active chat model and its state (Requirement 12). */
  list(): Promise<LlmIntegrationsState> {
    return apiRequest<LlmIntegrationsState>(BASE);
  },
  create(body: LlmIntegrationCreate): Promise<LlmIntegrationCreated> {
    return apiRequest<LlmIntegrationCreated>(BASE, json('POST', body));
  },
  /** A partial update: an absent field keeps its value; `api_key: ""` deletes the saved key. */
  update(item: Pick<LlmIntegrationItem, 'public_id'>, body: LlmIntegrationUpdate): Promise<LlmIntegrationUpdated> {
    return apiRequest<LlmIntegrationUpdated>(one(item), json('PUT', body));
  },
  setActive(item: Pick<LlmIntegrationItem, 'public_id'>, active: boolean, replace: boolean): Promise<LlmIntegrationsState> {
    return apiRequest<LlmIntegrationsState>(`${one(item)}/active`, json('PUT', {active, replace}));
  },
  remove(item: Pick<LlmIntegrationItem, 'public_id'>): Promise<LlmIntegrationsState> {
    return apiRequest<LlmIntegrationsState>(one(item), {method: 'DELETE'});
  },
  /** One server's models; a server failure is `ok: false` with its class (Requirement 14). */
  models(body: LlmModelsRequest): Promise<LlmModelsResult> {
    return apiRequest<LlmModelsResult>(`${BASE}/models`, json('POST', body));
  },
  inventory(): Promise<LlmInventory> {
    return apiRequest<LlmInventory>(`${BASE}/inventory`);
  },
  /** The server and chat-model steps; nothing is saved but `record` (Requirement 15). */
  test(body: Partial<LlmTestRequest>): Promise<LlmTestResult> {
    return apiRequest<LlmTestResult>(`${BASE}/test`, json('POST', body));
  },
};
