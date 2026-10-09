import {createContext, useContext} from 'react';
import type {LlmIntegrationsState} from '@/types/llm';

export interface LlmStateValue {
  /** The last answer of `GET /llm-integrations`; null until the first one arrives. */
  llm: LlmIntegrationsState | null;
  /** Grows with every new state; the AI page keys its cards on it, as the source redrew them. */
  version: number;
  /** The failure of the last read while there is no state yet. */
  failure: unknown;
  /** Read the state again (the shell does on opening and on every page change). */
  reload: () => Promise<void>;
  /** Take the state an AI page action answered with. */
  adopt: (state: LlmIntegrationsState) => void;
}

export const LlmStateContext = createContext<LlmStateValue | null>(null);

/**
 * The model connections' state shared by the admin shell (sidebar badge and system status;
 * search-settings Requirement 21) and the AI page (llm-connection Requirement 19).
 */
export function useLlmState(): LlmStateValue {
  const value = useContext(LlmStateContext);
  if (!value) throw new Error('useLlmState must be used inside LlmStateProvider');
  return value;
}
