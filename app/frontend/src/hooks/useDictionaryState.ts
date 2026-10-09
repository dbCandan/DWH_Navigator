import {createContext, useContext} from 'react';
import type {DictionaryState, DictionaryTable} from '@/types/dictionary';

export interface DictionaryStateValue {
  /** The last `GET /dictionary`; null until the first answer. */
  dictionary: DictionaryState | null;
  /** The active version's tables; null while they load or when there is no dictionary. */
  tables: DictionaryTable[] | null;
  /** The failure of the last read while there is nothing to show yet. */
  failure: unknown;
  reload: () => Promise<void>;
}

export const DictionaryStateContext = createContext<DictionaryStateValue | null>(null);

/**
 * The dictionary's state and table list, shared by the admin shell (badge, system status, the
 * command palette's "Tablolar") and the Sözlük page (dictionary-management Requirement 13).
 */
export function useDictionaryState(): DictionaryStateValue {
  const value = useContext(DictionaryStateContext);
  if (!value) throw new Error('useDictionaryState must be used inside DictionaryStateProvider');
  return value;
}
