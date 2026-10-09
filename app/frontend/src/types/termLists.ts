import type {components} from './api';

type Schemas = components['schemas'];

/** Term lists searched one term at a time (data-dictionary/PRDs/005-list-search). */
export type TermList = Schemas['TermListSnapshot'];
export type TermListPage = Schemas['TermListPage'];
export type TermListSummary = Schemas['TermListSummary'];
export type TermRow = Schemas['TermRow'];
export type TermListStatus = TermList['status'];
