import type {components} from './api';

type Schemas = components['schemas'];

/** Search and answer settings and the search index (data-dictionary/PRDs/009-search-settings). */
export type SearchSettings = Schemas['SearchSettings'];
export type SearchSettingSection = Schemas['SearchSettingSection'];
export type SearchSettingField = Schemas['SearchSettingField'];
export type SearchSettingsSaved = Schemas['SearchSettingsSaved'];
export type SettingValue = SearchSettings['values'][string];
export type SettingValues = SearchSettings['values'];
export type SearchIndexState = Schemas['SearchIndexState'];
export type SearchIndexRebuilt = Schemas['SearchIndexRebuilt'];
export type SearchIndexInput = SearchIndexState['stale_inputs'][number];
