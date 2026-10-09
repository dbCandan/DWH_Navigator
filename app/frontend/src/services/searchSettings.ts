import {apiRequest} from '@/lib/apiClient';
import type {SearchIndexRebuilt, SearchIndexState, SearchSettings, SearchSettingsSaved, SettingValues} from '@/types/search';

/** The search settings and the search index (data-dictionary/PRDs/009-search-settings, API contract). */
export const SearchSettingsService = {
  /** The schema, the effective values and the defaults (Requirement 2). */
  settings(): Promise<SearchSettings> {
    return apiRequest<SearchSettings>('/search-settings');
  },
  /** The changed values in one request; applied with the index when it needs it (Requirement 3, 6). */
  save(values: SettingValues): Promise<SearchSettingsSaved> {
    return apiRequest<SearchSettingsSaved>('/search-settings', {method: 'PATCH', body: JSON.stringify({values})});
  },
  index(): Promise<SearchIndexState> {
    return apiRequest<SearchIndexState>('/search-index');
  },
  /** Build the engine again from the current inputs (Requirement 14). */
  rebuild(): Promise<SearchIndexRebuilt> {
    return apiRequest<SearchIndexRebuilt>('/search-index/rebuilds', {method: 'POST'});
  },
};
