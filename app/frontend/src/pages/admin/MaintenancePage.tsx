import {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {adminPath} from '@/components/admin/nav';
import {PageHead} from '@/components/admin/PageHead';
import {Skeleton} from '@/components/admin/Skeleton';
import {SettingsCard} from '@/components/settings/SettingsCard';
import {useIntl} from '@/contexts/IntlContext';
import {useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useSearchState} from '@/hooks/useSearchState';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {dictionaryStatus, indexStatus, type IndexStatus} from '@/lib/adminStatus';
import {formatNumber, formatWhen} from '@/lib/format';
import {pageOfSection} from '@/lib/settingsDraft';
import {SavedAnswersService} from '@/services/savedAnswers';
import type {SavedAnswersSummary} from '@/types/analysis';
import type {SearchIndexState} from '@/types/search';
import './maintenance.css';

const PILL: Record<IndexStatus, {kind: string; key: string}> = {
  ok: {kind: 'ok', key: 'maintenance.index.ok'},
  building: {kind: 'warn', key: 'maintenance.index.building'},
  stale: {kind: 'warn', key: 'maintenance.index.stale'},
  empty: {kind: 'warn', key: 'maintenance.index.empty'},
  unknown: {kind: 'warn', key: 'maintenance.index.stale'},
};

/** The last failed build when it came after the serving index was built. */
function failedAfterBuild(index: SearchIndexState): string | null {
  const failure = index.last_failure;
  if (!failure) return null;
  if (index.built_at && new Date(failure.at).getTime() <= new Date(index.built_at).getTime()) return null;
  return failure.at;
}

/**
 * The kept answers' block under "Önceki cevaplar" (search-settings Requirement 16, 19): the
 * summary and "Önceki cevapları sil…". Without a summary (none kept, or the endpoints are not
 * served) it reads "henüz yok" and the button stays disabled.
 */
function SavedAnswers({summary, onCleared}: {summary: SavedAnswersSummary | null; onCleared: () => Promise<void>}) {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const [busy, setBusy] = useState(false);
  const total = summary?.total ?? 0;

  async function clear() {
    if (!window.confirm(t('maintenance.answers.confirm', {count: formatNumber(total)}))) return;
    setBusy(true);
    try {
      const answer = await SavedAnswersService.clear();
      toast(t('maintenance.answers.cleared'), [t('maintenance.answers.clearedLine', {count: formatNumber(answer.removed)})]);
      await onCleared();
    } catch (error) {
      reportUnreachable(error);
      toast(t('maintenance.answers.clearFailed'), [adminErrorText(error, t)], true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="sec-t">{t('maintenance.answers.title')}</div>
      <dl className="kv">
        <dt>{t('maintenance.answers.kept')}</dt>
        <dd>
          {total
            ? t('maintenance.answers.keptValue', {total: formatNumber(total), usable: formatNumber(summary?.usable)})
            : t('maintenance.answers.none')}
        </dd>
        {summary?.newest_at ? <dt>{t('maintenance.answers.newest')}</dt> : null}
        {summary?.newest_at ? <dd>{formatWhen(summary.newest_at, t)}</dd> : null}
      </dl>
      <p className="note">{t('maintenance.answers.note')}</p>
      <button className="btn danger" type="button" disabled={!total || busy} onClick={() => void clear()}>
        {t('maintenance.answers.clear')}
      </button>
    </div>
  );
}

/**
 * The "Bakım" page (search-settings Requirement 19; admin.html PAGES.bakim): the search index
 * card, then the "Önceki cevaplar" settings with the kept answers' block, in columns.
 */
export default function MaintenancePage() {
  const {t} = useIntl();
  const {settings, settingsFailure, index} = useSearchState();
  const {dictionary} = useDictionaryState();
  const rebuild = useIndexRebuild();
  const [rebuilding, setRebuilding] = useState(false);
  const [summary, setSummary] = useState<SavedAnswersSummary | null>(null);
  const label = t('admin.page.bakim.label');

  const readSummary = useCallback(async () => {
    try {
      setSummary(await SavedAnswersService.summary());
    } catch {
      setSummary(null);
    }
  }, []);

  useEffect(() => {
    let live = true;
    SavedAnswersService.summary().then(
      (answer) => live && setSummary(answer),
      () => live && setSummary(null),
    );
    return () => {
      live = false;
    };
  }, []);

  async function runRebuild() {
    setRebuilding(true);
    try {
      await rebuild();
    } finally {
      setRebuilding(false);
    }
  }

  const dict = dictionaryStatus(dictionary);
  const head = (
    <PageHead
      title={label}
      description={t('admin.page.bakim.description')}
      actions={
        <Link className="btn ghost" to={adminPath('sozluk')}>
          <Icon name="book" />
          {dict.state === 'none' ? t('maintenance.toDictionaryImport') : t('maintenance.toDictionary')}
        </Link>
      }
    />
  );
  if (!settings || !index)
    return (
      <section className="page on" id="p-bakim" aria-label={label}>
        {head}
        {settingsFailure ? (
          <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(settingsFailure, t)})}</div>
        ) : (
          <Skeleton />
        )}
      </section>
    );

  const ix = indexStatus(index);
  const pill = PILL[ix];
  const [digits, rows] = index.dictionary_version.split('-');
  const failedAt = failedAfterBuild(index);
  const sections = settings.sections
    .filter((section) => pageOfSection(section.page) === 'bakim')
    .sort((a, b) => Number(a.id === 'cache') - Number(b.id === 'cache'));

  return (
    <section className="page on" id="p-bakim" aria-label={label}>
      {head}
      <div className="fill scroll">
        <div className="cols">
          <section className="card" id="sec-index">
            <div className="card-h">
              <h2>{t('maintenance.index.title')}</h2>
              <span className={'pill ' + pill.kind}>{t(pill.key)}</span>
            </div>
            <p className="intro">{t('maintenance.index.intro')}</p>
            {ix === 'stale' ? (
              <div className="msg warn">
                {t('maintenance.index.mismatch', {
                  inputs: index.stale_inputs.map((input) => t(`maintenance.input.${input}`)).join(', '),
                })}
              </div>
            ) : null}
            {failedAt ? <div className="msg bad">{t('maintenance.index.lastFailed', {when: formatWhen(failedAt, t)})}</div> : null}
            <dl className="kv">
              <dt>{t('maintenance.index.dictionary')}</dt>
              <dd>
                {rows
                  ? t('maintenance.index.dictionaryValue', {columns: formatNumber(Number(rows)), version: digits.slice(0, 8)})
                  : t('maintenance.index.dictionaryNone')}
              </dd>
              <dt>{t('maintenance.index.built')}</dt>
              <dd>{index.built_at ? formatWhen(index.built_at, t) : '—'}</dd>
            </dl>
            <button
              className={'btn' + (ix === 'stale' ? ' primary' : '')}
              type="button"
              disabled={rebuilding}
              onClick={() => void runRebuild()}
            >
              {rebuilding ? (
                t('maintenance.index.rebuilding')
              ) : (
                <>
                  <Icon name="refresh" />
                  {t('maintenance.index.rebuild')}
                </>
              )}
            </button>
            <span className="note after-btn">{t('maintenance.index.rebuildNote')}</span>
          </section>
          {sections.map((section) => (
            <SettingsCard key={section.id} settings={settings} section={section}>
              {section.id === 'cache' ? <SavedAnswers summary={summary} onCleared={readSummary} /> : null}
            </SettingsCard>
          ))}
        </div>
      </div>
    </section>
  );
}
