import type {LlmIntegrationsState} from '@/types/llm';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** The chat model's state as the admin screen shows it (admin.html modelState()). */
export interface ModelStatus {
  /** `unknown` until the first answer arrives. */
  state: 'unknown' | 'none' | 'down' | 'ok';
  /** The active integration and its chat model, when there is one. */
  active: {public_id: string; name: string; model: string} | null;
  /** The sidebar's short name of the model (the last part of a path-like id). */
  label: string;
  /** "<name> üzerinden", the check's reason, or "Sorular cevaplanamaz". */
  detail: string;
}

const short = (model: string) => model.split('/').pop() ?? model;

/**
 * llm-connection Requirement 12's model state in the source's terms: `none` when no integration
 * is active, `down` with the check's message, `ok` with the integration's name.
 */
export function modelStatus(llm: LlmIntegrationsState | null, t: Translate): ModelStatus {
  if (llm === null) return {state: 'unknown', active: null, label: t('ai.status.unknown'), detail: ''};
  const state = llm.model_state;
  if (state.state === 'none' || llm.active === null)
    return {state: 'none', active: null, label: t('ai.status.none'), detail: t('ai.status.noneDetail')};
  const active = {public_id: llm.active.public_id, name: state.name ?? llm.active.name, model: state.model || llm.active.model};
  if (state.state === 'down') return {state: 'down', active, label: short(active.model), detail: state.reason};
  return {state: 'ok', active, label: short(active.model), detail: t('ai.status.via', {name: active.name})};
}
