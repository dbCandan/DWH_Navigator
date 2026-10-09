import type {components} from './api';

type Schemas = components['schemas'];

/** The term dictionary and the stopword list (data-dictionary/PRDs/002-vocabulary-management). */
export type TermItem = Schemas['TermItem'];
export type StopwordItem = Schemas['StopwordItem'];
export type VocabularyListName = Schemas['VocabularyListState']['list'];
export type VocabularyListState = Schemas['VocabularyListState'];
export type VocabularyListSaved = Schemas['VocabularyListSaved'];

/** The items of each list, by its name. */
export interface VocabularyItems {
  terms: TermItem[];
  stopwords: StopwordItem[];
}
