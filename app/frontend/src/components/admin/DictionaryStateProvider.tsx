import {useCallback, useMemo, useRef, useState, type ReactNode} from 'react';
import {DictionaryStateContext} from '@/hooks/useDictionaryState';
import {useToast} from '@/hooks/useToast';
import {DictionaryService} from '@/services/dictionary';
import type {DictionaryState, DictionaryTable} from '@/types/dictionary';

interface Held {
  dictionary: DictionaryState | null;
  tables: DictionaryTable[] | null;
  /** The version (`public_id`) the table list belongs to. */
  tablesOf: string | null;
  failure: unknown;
}

/**
 * Holds the dictionary's state for the admin shell. The table list is read again only when the
 * active version changes; a read that a newer one overtook is dropped.
 */
export function DictionaryStateProvider({children}: {children: ReactNode}) {
  const {reportUnreachable} = useToast();
  const [held, setHeld] = useState<Held>({dictionary: null, tables: null, tablesOf: null, failure: null});
  const latest = useRef(0);
  const tablesOf = useRef<string | null>(null);

  const reload = useCallback(async () => {
    const mine = ++latest.current;
    try {
      const dictionary = await DictionaryService.state();
      const version = dictionary.active?.public_id ?? null;
      if (version === null || version === tablesOf.current) {
        if (mine !== latest.current) return;
        if (version === null) tablesOf.current = null;
        setHeld((current) => ({
          dictionary,
          tables: version === null ? null : current.tables,
          tablesOf: version,
          failure: null,
        }));
        return;
      }
      const tables = await DictionaryService.tables();
      if (mine !== latest.current) return;
      tablesOf.current = version;
      setHeld({dictionary, tables, tablesOf: version, failure: null});
    } catch (error) {
      reportUnreachable(error);
      if (mine === latest.current) setHeld((current) => ({...current, failure: current.dictionary ? null : error}));
    }
  }, [reportUnreachable]);

  const value = useMemo(
    () => ({dictionary: held.dictionary, tables: held.tables, failure: held.failure, reload}),
    [held, reload],
  );
  return <DictionaryStateContext.Provider value={value}>{children}</DictionaryStateContext.Provider>;
}
