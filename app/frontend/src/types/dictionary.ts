import type {components} from './api';

type Schemas = components['schemas'];

/** The data dictionary (data-dictionary/PRDs/001-dictionary-management, API contract). */
export type DictionaryState = Schemas['DictionaryState'];
export type ActiveDictionaryVersion = Schemas['ActiveDictionaryVersion'];
export type DictionaryVersionSummary = Schemas['DictionaryVersionSummary'];
export type DictionaryTable = Schemas['DictionaryTable'];
export type DictionaryTablesPage = Schemas['DictionaryTablesPage'];
export type DictionaryTableRecords = Schemas['DictionaryTableRecords'];
