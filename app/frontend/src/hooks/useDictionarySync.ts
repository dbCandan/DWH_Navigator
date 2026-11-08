import {useCallback, useEffect, useRef, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useAdminRefresh} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useSearchState} from '@/hooks/useSearchState';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {ApiError} from '@/lib/apiClient';
import {runFailureText} from '@/lib/dictionarySync';
import {DictionarySyncService} from '@/services/dictionarySync';
import type {DictionaryVersion, SyncPage, SyncRunSummary} from '@/types/dictionarySync';

const POLL_MS = 2000;
export const RUNS_PAGE_SIZE = 20;

export interface DictionarySync {
  runs: SyncRunSummary[] | null;
  runsTotal: number;
  runsPage: number;
  versions: DictionaryVersion[] | null;
  /** The run the server is working on, as last read. */
  running: SyncRunSummary | null;
  failure: unknown;
  start: () => Promise<void>;
  restore: (version: DictionaryVersion) => Promise<void>;
  showRuns: (page: number) => void;
  /** Follow a run an action left running, or read the lists again after one that settled it. */
  adopt: (run: SyncRunSummary) => Promise<void>;
  /** Read the history, the versions and the shell's states again (after an Excel import). */
  settle: () => Promise<void>;
}

/**
 * The Sözlük page's run state (dictionary-sync Requirement 2, 9, 10). The run lives on the server:
 * opening the page finds a running one in the list and follows it, so leaving the page loses
 * nothing. A run is read every 2 seconds until it ends; a failed read does not end it. `onFinished`
 * gets a run that ended while it was followed here.
 */
export function useDictionarySync(onFinished: (run: SyncRunSummary) => void): DictionarySync {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const {reload: reloadDictionary} = useDictionaryState();
  const {reloadIndex} = useSearchState();
  const refresh = useAdminRefresh();
  const [runs, setRuns] = useState<SyncRunSummary[] | null>(null);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsPage, setRunsPage] = useState(1);
  const [versions, setVersions] = useState<DictionaryVersion[] | null>(null);
  const [running, setRunning] = useState<SyncRunSummary | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const page = useRef(1);
  const reads = useRef(0);
  const finished = useRef(onFinished);
  useEffect(() => {
    finished.current = onFinished;
  });

  const adoptRuns = useCallback((answer: SyncPage<SyncRunSummary>) => {
    setRuns(answer.items);
    setRunsTotal(answer.total);
    setRunsPage(answer.page);
    setFailure(null);
  }, []);

  /** One page of the history; a read that a newer one overtook is dropped. */
  const readRuns = useCallback(async () => {
    const mine = ++reads.current;
    const answer = await DictionarySyncService.runs(page.current, RUNS_PAGE_SIZE);
    if (mine !== reads.current) return null;
    adoptRuns(answer);
    return answer.items;
  }, [adoptRuns]);

  const readLists = useCallback(async () => {
    try {
      const [items, list] = await Promise.all([readRuns(), DictionarySyncService.versions()]);
      setVersions(list);
      return items;
    } catch (error) {
      reportUnreachable(error);
      setFailure(error);
      return null;
    }
  }, [readRuns, reportUnreachable]);

  useEffect(() => {
    let live = true;
    Promise.all([DictionarySyncService.runs(1, RUNS_PAGE_SIZE), DictionarySyncService.versions()]).then(
      ([answer, list]) => {
        if (!live) return;
        adoptRuns(answer);
        setVersions(list);
        if (!answer.items.length) return;
        const current = answer.items.find((run) => run.status === 'running');
        if (current) {
          setRunning(current);
          return;
        }
        // A run that ended while nobody was here changed the version the shell still holds.
        void reloadDictionary();
        void reloadIndex();
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (live) setFailure(error);
      },
    );
    return () => {
      live = false;
    };
  }, [adoptRuns, reloadDictionary, reloadIndex, reportUnreachable]);

  const settle = useCallback(async () => {
    await Promise.all([readLists(), refresh()]);
  }, [readLists, refresh]);

  const runningId = running?.public_id ?? null;
  useEffect(() => {
    if (runningId === null) return;
    let live = true;
    let timer = 0;
    const poll = async () => {
      try {
        const run = await DictionarySyncService.run(runningId);
        if (!live) return;
        if (run.status !== 'running') {
          setRunning(null);
          const bad = run.status === 'failed' || run.status === 'interrupted';
          toast(t(`dictionary.sync.status.${run.status}`), [runFailureText(run, t) || null], bad);
          await settle();
          if (live) finished.current(run);
          return;
        }
        setRunning(run);
      } catch (error) {
        if (!live) return;
        if (error instanceof ApiError && error.status === 404) {
          setRunning(null);
          await settle();
          return;
        }
        reportUnreachable(error);
      }
      timer = window.setTimeout(() => void poll(), POLL_MS);
    };
    timer = window.setTimeout(() => void poll(), POLL_MS);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [runningId, t, toast, reportUnreachable, settle]);

  const adopt = useCallback(
    async (run: SyncRunSummary) => {
      if (run.status === 'running') {
        setRunning(run);
        await readLists();
      } else await settle();
    },
    [readLists, settle],
  );

  /** A run answered by the server; "already running" means another one is to be followed. */
  const begin = useCallback(
    async (request: () => Promise<SyncRunSummary>, failedTitle: string) => {
      try {
        await adopt(await request());
      } catch (error) {
        reportUnreachable(error);
        toast(t(failedTitle), [adminErrorText(error, t)], true);
        if (error instanceof ApiError && error.code === 'dictionary_sync_in_progress') {
          const current = (await readLists())?.find((run) => run.status === 'running');
          if (current) setRunning(current);
        }
      }
    },
    [adopt, readLists, reportUnreachable, t, toast],
  );

  const start = useCallback(() => begin(() => DictionarySyncService.start(), 'dictionary.sync.startFailed'), [begin]);
  const restore = useCallback(
    (version: DictionaryVersion) => begin(() => DictionarySyncService.restore(version.public_id), 'dictionary.versions.restoreFailed'),
    [begin],
  );

  const showRuns = useCallback(
    (next: number) => {
      page.current = next;
      readRuns().catch((error: unknown) => {
        reportUnreachable(error);
        toast(t('dictionary.runs.failed'), [adminErrorText(error, t)], true);
      });
    },
    [readRuns, reportUnreachable, t, toast],
  );

  return {runs, runsTotal, runsPage, versions, running, failure, start, restore, showRuns, adopt, settle};
}
