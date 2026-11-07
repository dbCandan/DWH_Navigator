import {useCallback, useEffect, useRef, useState} from 'react';
import {forgetTabList, rememberTabList, recallTabList} from '@/lib/tabList';
import {TermListService} from '@/services/termLists';
import type {TermList} from '@/types/termLists';

/** How often a running list is asked again (list-search Requirement 17, Decision 7). */
export const LIST_POLL_MS = 1500;

/** How an upload ended. */
export type ListStart =
  | {kind: 'started'}
  /** The person's own list runs: nothing is uploaded, the running list is shown. */
  | {kind: 'running'}
  | {kind: 'refused'; error: unknown};

/**
 * The person's term list on the main screen (list-search Requirement 11, 15, 17; Decision 15):
 * the tab's own list is kept in `sessionStorage`, a running list is asked again every 1.5 seconds
 * and not at all once it stopped. A failed poll stops following it (index.html Bulk.refresh). The
 * main screen does not call the Listeler endpoint on page open; a new tab opens empty.
 */
export function useTermList() {
  const [list, setList] = useState<TermList | null>(null);
  const [following, setFollowing] = useState(false);
  /** Bumped by every new answer of the list (the pill shows again with it). */
  const [polls, setPolls] = useState(0);
  const mounted = useRef(true);
  const current = useRef<TermList | null>(null);
  useEffect(() => {
    current.current = list;
  }, [list]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const take = useCallback((next: TermList) => {
    if (!mounted.current) return;
    setList(next);
    setFollowing(true);
    rememberTabList(next.id);
  }, []);

  // Reload in the same tab: the sessionStorage id reads the list once; nothing is fetched
  // without a remembered id, so a fresh tab opens empty (Decision 15).
  useEffect(() => {
    const id = recallTabList();
    if (id === null) return;
    let live = true;
    TermListService.get(id).then(
      (found) => {
        if (live && current.current === null) take(found);
      },
      () => {
        if (live) forgetTabList(id);
      },
    );
    return () => {
      live = false;
    };
  }, [take]);

  // Poll while the list runs; nothing once it has stopped (Decision 7).
  useEffect(() => {
    if (list === null || !following || list.status !== 'running') return;
    const id = list.id;
    const timer = window.setTimeout(() => {
      TermListService.get(id).then(
        (next) => {
          if (!mounted.current || current.current?.id !== id) return;
          setList(next);
          setPolls((n) => n + 1);
        },
        () => {
          if (mounted.current && current.current?.id === id) setFollowing(false);
        },
      );
    }, LIST_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [list, following]);

  const start = useCallback(
    async (file: File): Promise<ListStart> => {
      const known = current.current;
      if (known && known.status === 'running') return {kind: 'running'};
      try {
        take(await TermListService.start(file));
        return {kind: 'started'};
      } catch (error) {
        return {kind: 'refused', error};
      }
    },
    [take],
  );

  /** "■ Durdur": a failed request shows nothing; the view is drawn again (Requirement 17). */
  const stop = useCallback(async () => {
    const known = current.current;
    if (!known) return;
    try {
      take(await TermListService.cancel(known.id));
    } catch {
      // nothing is shown; the running list is still polled
    }
  }, [take]);

  /** "▶ Devam et": a refusal is shown in the browser's alert, as in the source (Requirement 17). */
  const resume = useCallback(async (): Promise<unknown> => {
    const known = current.current;
    if (!known) return null;
    try {
      take(await TermListService.resume(known.id));
      return null;
    } catch (error) {
      return error;
    }
  }, [take]);

  return {list, following, polls, start, stop, resume};
}
