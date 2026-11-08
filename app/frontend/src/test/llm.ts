import type {LlmIntegrationItem, LlmIntegrationsState} from '@/types/llm';

let created = 0;

/** A synthetic integration (no real server, model or key). */
export function integration(name: string, overrides: Partial<LlmIntegrationItem> = {}): LlmIntegrationItem {
  return {
    public_id: `00000000-0000-4000-8000-${String(++created).padStart(12, '0')}`,
    name,
    endpoint: 'http://10.0.0.5:8000/v1',
    has_key: false,
    active: false,
    chat_model: '',
    temperature: 0,
    timeout_seconds: 900,
    reasoning_effort: 'none',
    seed: 42,
    generation_model: '',
    generation_reasoning_effort: 'inherit',
    judge_reasoning_effort: 'inherit',
    last_test: null,
    created_at: '2026-10-08T08:00:00Z',
    updated_at: '2026-10-08T08:00:00Z',
    ...overrides,
  };
}

/** `GET /llm-integrations` for these integrations; the active one is `ok` unless told otherwise. */
export function llmState(
  items: LlmIntegrationItem[] = [],
  overrides: Partial<LlmIntegrationsState> = {},
): LlmIntegrationsState {
  const active = items.find((item) => item.active) ?? null;
  return {
    items,
    total: items.length,
    active: active ? {public_id: active.public_id, name: active.name, model: active.chat_model} : null,
    model_state: active
      ? {state: 'ok', model: active.chat_model, code: null, reason: '', name: active.name}
      : {state: 'none', model: '', code: 'not_configured', reason: 'Sohbet modeli bağlı değil', name: null},
    environment: 'local',
    accepts_http: true,
    key_storage: true,
    ...overrides,
  };
}
