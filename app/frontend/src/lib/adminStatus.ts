import type {ActiveDictionaryVersion, DictionaryState} from '@/types/dictionary';
import type {SearchIndexState} from '@/types/search';

/**
 * The dictionary's state in the admin screen's terms (admin.html dictState()): `unknown` until
 * the first answer, `none` before the first import, `stale` when the serving index was built
 * from another version, else `ok`.
 */
export interface DictionaryStatus {
  state: 'unknown' | 'none' | 'stale' | 'ok';
  active: ActiveDictionaryVersion | null;
}

export function dictionaryStatus(dictionary: DictionaryState | null): DictionaryStatus {
  if (dictionary === null) return {state: 'unknown', active: null};
  const active = dictionary.active;
  if (active === null) return {state: 'none', active: null};
  return {state: dictionary.index_dictionary_version === active.version ? 'ok' : 'stale', active};
}

/**
 * The search index's state as the sidebar and the Bakım page name it (search-settings
 * Requirement 15, 19, 21): `building`, `stale`, `empty` (0 columns) or `ok`.
 */
export type IndexStatus = 'unknown' | 'building' | 'stale' | 'empty' | 'ok';

export function indexStatus(index: SearchIndexState | null): IndexStatus {
  if (index === null) return 'unknown';
  if (index.state === 'building') return 'building';
  if (index.state === 'stale') return 'stale';
  return index.columns === 0 ? 'empty' : 'ok';
}

/** "abc123def456" from "abc123def456-11136": the version's first 12 hex digits. */
export const versionDigits = (version: string) => version.split('-')[0];
