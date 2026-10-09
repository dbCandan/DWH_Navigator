import {createContext, useContext} from 'react';
import type {SearchIndexState, SearchSettings, SettingValue, SettingValues} from '@/types/search';

export interface SearchStateValue {
  /** The last `GET /search-settings`; null until the first answer. */
  settings: SearchSettings | null;
  /** The draft: saved values with the edits not saved yet (search-settings Requirement 23). */
  form: SettingValues;
  /** The failure of the last settings read while there are no settings yet. */
  settingsFailure: unknown;
  /** The last `GET /search-index`; null until the first answer. */
  index: SearchIndexState | null;
  reloadSettings: () => Promise<void>;
  reloadIndex: () => Promise<void>;
  /** Take the settings or the index state an action answered with. */
  adoptSettings: (settings: SearchSettings) => void;
  adoptIndex: (index: SearchIndexState) => void;
  setValue: (key: string, value: SettingValue) => void;
  /** Every draft value back to its saved one ("Geri al"). */
  revert: () => void;
}

export const SearchStateContext = createContext<SearchStateValue | null>(null);

/**
 * The search settings' draft and the search index's state, shared by the admin shell (badges,
 * system status, the unsaved-changes bar, the command palette) and the settings pages.
 */
export function useSearchState(): SearchStateValue {
  const value = useContext(SearchStateContext);
  if (!value) throw new Error('useSearchState must be used inside SearchStateProvider');
  return value;
}
