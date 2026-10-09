import {useCallback, useEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {SearchStateContext} from '@/hooks/useSearchState';
import {useToast} from '@/hooks/useToast';
import {adoptDraft} from '@/lib/settingsDraft';
import {SearchSettingsService} from '@/services/searchSettings';
import type {SearchIndexState, SearchSettings, SettingValue, SettingValues} from '@/types/search';

const BUILDING_POLL_MS = 2000;

interface Held {
  settings: SearchSettings | null;
  form: SettingValues;
  failure: unknown;
}

/**
 * Holds the search settings with their draft and the search index's state for the admin shell.
 * New values from the server keep the unsaved edits; a read that a newer answer overtook is
 * dropped; while the index is building it is read again every 2 seconds (search-settings
 * Requirement 21, 23).
 */
export function SearchStateProvider({children}: {children: ReactNode}) {
  const {reportUnreachable} = useToast();
  const [held, setHeld] = useState<Held>({settings: null, form: {}, failure: null});
  const [index, setIndex] = useState<SearchIndexState | null>(null);
  const settingsRead = useRef(0);
  const indexRead = useRef(0);

  const adoptSettings = useCallback((settings: SearchSettings) => {
    settingsRead.current += 1;
    setHeld((current) => ({settings, form: adoptDraft(current.settings, current.form, settings), failure: null}));
  }, []);

  const reloadSettings = useCallback(async () => {
    const mine = ++settingsRead.current;
    try {
      const settings = await SearchSettingsService.settings();
      if (mine === settingsRead.current)
        setHeld((current) => ({settings, form: adoptDraft(current.settings, current.form, settings), failure: null}));
    } catch (error) {
      reportUnreachable(error);
      if (mine === settingsRead.current) setHeld((current) => ({...current, failure: current.settings ? null : error}));
    }
  }, [reportUnreachable]);

  const adoptIndex = useCallback((state: SearchIndexState) => {
    indexRead.current += 1;
    setIndex(state);
  }, []);

  const reloadIndex = useCallback(async () => {
    const mine = ++indexRead.current;
    try {
      const state = await SearchSettingsService.index();
      if (mine === indexRead.current) setIndex(state);
    } catch (error) {
      reportUnreachable(error);
    }
  }, [reportUnreachable]);

  const building = index?.state === 'building';
  useEffect(() => {
    if (!building) return;
    const timer = window.setInterval(() => void reloadIndex(), BUILDING_POLL_MS);
    return () => window.clearInterval(timer);
  }, [building, reloadIndex]);

  const setValue = useCallback((key: string, value: SettingValue) => {
    setHeld((current) => ({...current, form: {...current.form, [key]: value}}));
  }, []);

  const revert = useCallback(() => {
    setHeld((current) => ({...current, form: current.settings ? {...current.settings.values} : {}}));
  }, []);

  const value = useMemo(
    () => ({
      settings: held.settings,
      form: held.form,
      settingsFailure: held.failure,
      index,
      reloadSettings,
      reloadIndex,
      adoptSettings,
      adoptIndex,
      setValue,
      revert,
    }),
    [held, index, reloadSettings, reloadIndex, adoptSettings, adoptIndex, setValue, revert],
  );
  return <SearchStateContext.Provider value={value}>{children}</SearchStateContext.Provider>;
}
