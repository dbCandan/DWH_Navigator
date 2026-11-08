import {useCallback} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useSearchState} from '@/hooks/useSearchState';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {versionDigits} from '@/lib/adminStatus';
import {confirmAction} from '@/lib/confirm';
import {isWorkbookName} from '@/lib/excelUpload';
import {formatDuration, formatNumber} from '@/lib/format';
import {changedKeys, settingFields} from '@/lib/settingsDraft';
import {DictionaryService} from '@/services/dictionary';
import {SearchSettingsService} from '@/services/searchSettings';

/**
 * Read the admin shell's states again after an operation (search-settings Requirement 21):
 * the settings, the dictionary and the search index.
 */
export function useAdminRefresh(): () => Promise<void> {
  const {reloadSettings, reloadIndex} = useSearchState();
  const {reload: reloadDictionary} = useDictionaryState();
  return useCallback(async () => {
    await Promise.all([reloadSettings(), reloadIndex(), reloadDictionary()]);
  }, [reloadSettings, reloadIndex, reloadDictionary]);
}

/**
 * "Arama indeksini yeniden kur" (search-settings Requirement 14; admin.html reindex()): the
 * notice gives the columns, tables and the seconds the request took, as the source measured them.
 */
export function useIndexRebuild(): () => Promise<void> {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const {adoptIndex} = useSearchState();
  const refresh = useAdminRefresh();
  return useCallback(async () => {
    try {
      const started = performance.now();
      const answer = await SearchSettingsService.rebuild();
      adoptIndex(answer);
      toast(t('admin.index.rebuilt'), [
        t('admin.index.rebuiltLine', {
          columns: formatNumber(answer.columns),
          objects: formatNumber(answer.objects),
          seconds: ((performance.now() - started) / 1000).toFixed(1),
        }),
      ]);
      await refresh();
    } catch (error) {
      reportUnreachable(error);
      toast(t('admin.index.failed'), [adminErrorText(error, t)], true);
    }
  }, [t, toast, reportUnreachable, adoptIndex, refresh]);
}

/**
 * "Kaydet ve uygula" (search-settings Requirement 23): every changed key in one request; on
 * success the changed labels and, when the word index was rebuilt, its duration; on failure the
 * draft stays.
 */
export function useSettingsSave(): () => Promise<void> {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const {settings, form, adoptSettings, adoptIndex} = useSearchState();
  const refresh = useAdminRefresh();
  return useCallback(async () => {
    if (!settings) return;
    const fields = settingFields(settings);
    const keys = changedKeys(settings, form);
    try {
      const answer = await SearchSettingsService.save(Object.fromEntries(keys.map((key) => [key, form[key]])));
      adoptSettings({...settings, values: answer.values});
      adoptIndex(answer.index);
      const labels = answer.changed.map((key) => fields.get(key)?.label ?? key);
      const reindexed = answer.changed.some((key) => fields.get(key)?.effect === 'reindex');
      toast(t('admin.save.saved'), [
        t('admin.save.changed', {labels: labels.join(', ') || '—'}),
        reindexed && t('admin.save.reindexed', {duration: formatDuration(answer.elapsed_ms, t)}),
      ]);
      await refresh();
    } catch (error) {
      reportUnreachable(error);
      toast(t('admin.save.failed'), [adminErrorText(error, t)], true);
    }
  }, [t, toast, reportUnreachable, settings, form, adoptSettings, adoptIndex, refresh]);
}

/** A download through the shared client; a failure is a notice (user-accounts Requirement 12). */
export function useDownload(): (run: () => Promise<unknown>) => Promise<void> {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  return useCallback(
    async (run: () => Promise<unknown>) => {
      try {
        await run();
      } catch (error) {
        reportUnreachable(error);
        toast(t('admin.download.failed'), [adminErrorText(error, t)], true);
      }
    },
    [t, toast, reportUnreachable],
  );
}

/**
 * The dictionary's Excel import (dictionary-management Requirement 15; dictionary-sync
 * Requirement 13): only `.xlsx`; replacing an active dictionary is confirmed first; a notice stays
 * while the file is read, checked and indexed; then `onDone` reads the page's lists again. The
 * server's Turkish message explains a refused workbook.
 */
export function useDictionaryImport(onDone: () => Promise<void>): (file: File) => Promise<void> {
  const {t} = useIntl();
  const {toast, hold, reportUnreachable} = useToast();
  const {dictionary} = useDictionaryState();
  const {adoptIndex} = useSearchState();
  return useCallback(
    async (file: File) => {
      if (!isWorkbookName(file.name)) {
        toast(t('admin.excel.notExcel'), [file.name], true);
        return;
      }
      if (dictionary?.active) {
        const question = t('dictionary.import.confirm', {name: file.name});
        if (!(await confirmAction(question, {action: t('dictionary.import.action')}))) return;
      }
      const dismiss = hold(t('dictionary.import.running'), [t('dictionary.import.runningLine', {name: file.name})]);
      try {
        const answer = await DictionaryService.importWorkbook(file);
        dismiss();
        const version = answer.version;
        if (answer.changed)
          toast(t('dictionary.import.done'), [
            t('dictionary.import.doneCounts', {
              columns: formatNumber(version.column_count),
              objects: formatNumber(version.object_count),
              source: version.source_name,
            }),
            t('dictionary.import.doneIndexed'),
            answer.warnings.length > 0 &&
              t('dictionary.import.doneWarnings', {
                count: version.warning_count,
                warnings: answer.warnings.slice(0, 3).join(' · '),
              }),
          ]);
        else toast(t('dictionary.import.unchanged'), [t('dictionary.import.unchangedLine', {version: versionDigits(version.version)})]);
        adoptIndex(answer.index);
        await onDone();
      } catch (error) {
        dismiss();
        reportUnreachable(error);
        toast(t('dictionary.import.failed'), [adminErrorText(error, t)], true);
      }
    },
    [t, toast, hold, reportUnreachable, dictionary, adoptIndex, onDone],
  );
}
