import {useCallback, useMemo, useState, type ReactNode} from 'react';
import {VocabularyDraftContext} from '@/hooks/useVocabularyDraft';
import type {
  StopwordItem,
  TermItem,
  VocabularyItems,
  VocabularyListName,
  VocabularyListState,
} from '@/types/vocabulary';

type Saved = Record<VocabularyListName, VocabularyListState>;

const copyTerms = (items: readonly TermItem[]): TermItem[] => items.map((item) => ({...item, equivalents: [...item.equivalents]}));
const copyStops = (items: readonly StopwordItem[]): StopwordItem[] => items.map((item) => ({...item}));
const termsOf = (state: VocabularyListState) => state.items as TermItem[];
const stopsOf = (state: VocabularyListState) => state.items as StopwordItem[];

/** A list's content in a fixed field order, so the comparison does not depend on key order. */
function content(list: VocabularyListName, items: readonly (TermItem | StopwordItem)[]): string {
  return JSON.stringify(
    list === 'terms'
      ? (items as TermItem[]).map((item) => [item.term, item.equivalents, item.domain, item.note])
      : (items as StopwordItem[]).map((item) => [item.word, item.group]),
  );
}

/** Holds the word lists' saved state and draft for the admin shell. */
export function VocabularyDraftProvider({children}: {children: ReactNode}) {
  const [saved, setSaved] = useState<Saved | null>(null);
  const [draft, setDraft] = useState<VocabularyItems>({terms: [], stopwords: []});

  const dirty = useCallback(
    (list: VocabularyListName) =>
      saved !== null && content(list, draft[list]) !== content(list, saved[list].items),
    [saved, draft],
  );

  const adoptBoth = useCallback((terms: VocabularyListState, stopwords: VocabularyListState) => {
    setSaved({terms, stopwords});
    setDraft({terms: copyTerms(termsOf(terms)), stopwords: copyStops(stopsOf(stopwords))});
  }, []);

  const adoptOne = useCallback((state: VocabularyListState) => {
    setSaved((current) => (current ? {...current, [state.list]: state} : current));
    setDraft((current) =>
      state.list === 'terms'
        ? {...current, terms: copyTerms(termsOf(state))}
        : {...current, stopwords: copyStops(stopsOf(state))},
    );
  }, []);

  const edit = useCallback(<L extends VocabularyListName>(list: L, items: VocabularyItems[L]) => {
    setDraft((current) => ({...current, [list]: items}));
  }, []);

  const revert = useCallback(
    (list: VocabularyListName) => {
      if (!saved) return;
      setDraft((current) =>
        list === 'terms'
          ? {...current, terms: copyTerms(termsOf(saved.terms))}
          : {...current, stopwords: copyStops(stopsOf(saved.stopwords))},
      );
    },
    [saved],
  );

  const value = useMemo(
    () => ({saved, draft, dirty, adoptBoth, adoptOne, edit, revert}),
    [saved, draft, dirty, adoptBoth, adoptOne, edit, revert],
  );
  return <VocabularyDraftContext.Provider value={value}>{children}</VocabularyDraftContext.Provider>;
}
