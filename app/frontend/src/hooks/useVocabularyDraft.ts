import {createContext, useContext} from 'react';
import type {VocabularyItems, VocabularyListName, VocabularyListState} from '@/types/vocabulary';

export interface VocabularyDraftValue {
  /** The saved lists; null until both arrived. */
  saved: Record<VocabularyListName, VocabularyListState> | null;
  /** The lists as edited on the page, kept while moving between admin pages. */
  draft: VocabularyItems;
  /** True when a list's draft differs from its saved items. */
  dirty: (list: VocabularyListName) => boolean;
  /** Both lists from the server: the edits are dropped. */
  adoptBoth: (terms: VocabularyListState, stopwords: VocabularyListState) => void;
  /** One list written on the server; the other list keeps its own edits. */
  adoptOne: (state: VocabularyListState) => void;
  edit: <L extends VocabularyListName>(list: L, items: VocabularyItems[L]) => void;
  /** A list's draft back to its saved items ("Geri al"). */
  revert: (list: VocabularyListName) => void;
}

export const VocabularyDraftContext = createContext<VocabularyDraftValue | null>(null);

/**
 * The word lists' saved state and draft (vocabulary-management Requirement 13): edits gather on
 * the Kelimeler page's cards and survive moving between admin pages; the admin shell asks before
 * leaving while one is unsaved.
 */
export function useVocabularyDraft(): VocabularyDraftValue {
  const value = useContext(VocabularyDraftContext);
  if (!value) throw new Error('useVocabularyDraft must be used inside VocabularyDraftProvider');
  return value;
}
