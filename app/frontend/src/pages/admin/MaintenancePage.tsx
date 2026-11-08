import {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {adminPath} from '@/components/admin/nav';
import {PageHero} from '@/components/admin/PageHero';
import {Skeleton} from '@/components/admin/Skeleton';
import {SettingsCard} from '@/components/settings/SettingsCard';
import {useIntl} from '@/contexts/IntlContext';
import {useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useSearchState} from '@/hooks/useSearchState';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {dictionaryStatus, indexStatus, type IndexStatus} from '@/lib/adminStatus';
import {confirmAction} from '@/lib/confirm';
import {formatNumber, formatWhen} from '@/lib/format';
import {pageOfSection} from '@/lib/settingsDraft';
import {SavedAnswersService} from '@/services/savedAnswers';
import type {SavedAnswersSummary} from '@/types/analysis';
import type {SearchIndexState} from '@/types/search';
import './maintenance.css';

const PILL: Record<IndexStatus, {kind: 'ok' | 'warn'; key: string}> = {
  ok: {kind: 'ok', key: 'maintenance.index.ok'},
  building: {kind: 'warn', key: 'maintenance.index.building'},
  stale: {kind: 'warn', key: 'maintenance.index.stale'},
  empty: {kind: 'warn', key: 'maintenance.index.empty'},
  unknown: {kind: 'warn', key: 'maintenance.index.stale'},
};

type Input = SearchIndexState['stale_inputs'][number];

/** What the index is built from, in order, and where each is edited. */
const INPUTS: readonly {input: Input; to: string}[] = [
  {input: 'dictionary', to: adminPath('sozluk')},
  {input: 'terms', to: adminPath('kelimeler')},
  {input: 'stopwords', to: `${adminPath('kelimeler')}?liste=durak`},
  {input: 'settings', to: adminPath('arama')},
];

/** The last failed build when it came after the serving index was built. */
function failedAfterBuild(index: SearchIndexState): string | null {
  const failure = index.last_failure;
  if (!failure) return null;
  if (index.built_at && new Date(failure.at).getTime() <= new Date(index.built_at).getTime()) return null;
  return failure.at;
}

/**
 * The kept answers' block in the "Önceki cevaplar" panel (search-settings Requirement 16, 19): how
 * many are kept, the share still usable as a bar, the newest, and "Önceki cevapları sil…".
 * Without a summary (none kept, or the endpoints are not served) it reads "henüz yok" and the
 * button stays disabled.
 */
function SavedAnswers({summary, onCleared}: {summary: SavedAnswersSummary | null; onCleared: () => Promise<void>}) {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const [busy, setBusy] = useState(false);
  const total = summary?.total ?? 0;
  const usable = summary?.usable ?? 0;

  async function clear() {
    const question = t('maintenance.answers.confirm', {count: formatNumber(total)});
    if (!(await confirmAction(question, {action: t('maintenance.answers.confirmAction'), danger: true}))) return;
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
    <div className="kept">
      <div className="sec-t">{t('maintenance.answers.title')}</div>
      <div className="kept-n">
        <b>{total ? formatNumber(total) : '—'}</b>
        <span>
          {total
            ? t('maintenance.answers.keptValue', {total: formatNumber(total), usable: formatNumber(usable)})
            : t('maintenance.answers.none')}
        </span>
      </div>
      {total ? (
        <div className="share" title={t('maintenance.answers.shareTip', {usable: formatNumber(usable), total: formatNumber(total)})}>
          <i style={{width: `${Math.round((100 * usable) / total)}%`}} />
        </div>
      ) : null}
      {summary?.newest_at ? (
        <dl className="kv">
          <dt>{t('maintenance.answers.newest')}</dt>
          <dd>{formatWhen(summary.newest_at, t)}</dd>
        </dl>
      ) : null}
      <p className="note">{t('maintenance.answers.note')}</p>
      <button className="btn danger" type="button" disabled={!total || busy} onClick={() => void clear()}>
        {t('maintenance.answers.clear')}
      </button>
    </div>
  );
}

/**
 * The "Bakım" page (search-settings Requirement 19): the hero gives the index's state and the kept
 * answers; the index console shows its state as a ring, what it is built from (each input with
 * where it is edited, a stale one marked) and the rebuild; beside it the "Önceki cevaplar" panel.
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
  const toDictionary = (
    <Link className="btn" to={adminPath('sozluk')}>
      <Icon name="book" />
      {dict.state === 'none' ? t('maintenance.toDictionarySetup') : t('maintenance.toDictionary')}
    </Link>
  );
  if (!settings || !index)
    return (
      <section className="page on" id="p-bakim" aria-label={label}>
        <PageHero icon="wrench" title={label} description={t('admin.page.bakim.description')} actions={toDictionary} />
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
  const total = summary?.total ?? 0;
  const usable = summary?.usable ?? 0;
  const stale = new Set(index.stale_inputs);

  return (
    <section className="page on" id="p-bakim" aria-label={label}>
      <PageHero
        icon="wrench"
        title={label}
        description={t('admin.page.bakim.description')}
        actions={toDictionary}
        stats={[
          {label: t('maintenance.stat.index'), value: t(pill.key), tone: failedAt ? 'bad' : pill.kind},
          {
            label: t('maintenance.index.built'),
            value: index.built_at ? formatWhen(index.built_at, t) : '—',
            note: rows ? t('maintenance.stat.columns', {columns: formatNumber(Number(rows))}) : undefined,
          },
          {label: t('maintenance.stat.kept'), value: formatNumber(total), note: t('maintenance.stat.usable', {count: formatNumber(usable)})},
        ]}
      />
      <div className="fill scroll">
        <div className="mt-grid">
          <section className="panel mt-index" id="sec-index">
            <div className="panel-h">
              <h2>{t('maintenance.index.title')}</h2>
              <span className={'pill ' + pill.kind}>{t(pill.key)}</span>
            </div>
            <div className="panel-b">
              <div className="mt-state">
                <div className={'ring ' + (failedAt ? 'bad' : pill.kind)}>
                  <Icon name={pill.kind === 'ok' && !failedAt ? 'check' : 'alert'} />
                </div>
                <p className="intro">{t('maintenance.index.intro')}</p>
              </div>
              {ix === 'stale' ? (
                <div className="msg warn">
                  {t('maintenance.index.mismatch', {
                    inputs: index.stale_inputs.map((input) => t(`maintenance.input.${input}`)).join(', '),
                  })}
                </div>
              ) : null}
              {failedAt ? <div className="msg bad">{t('maintenance.index.lastFailed', {when: formatWhen(failedAt, t)})}</div> : null}
              <div className="sec-t">{t('maintenance.inputs.title')}</div>
              <ol className="mt-inputs">
                {INPUTS.map(({input, to}) => (
                  <li key={input} className={stale.has(input) ? 'stale' : 'ok'}>
                    <span className="mark" aria-hidden="true">
                      <Icon name={stale.has(input) ? 'alert' : 'check'} />
                    </span>
                    <span className="nm">
                      <b>{t(`maintenance.inputTitle.${input}`)}</b>
                      <small>
                        {input === 'dictionary'
                          ? rows
                            ? t('maintenance.index.dictionaryValue', {columns: formatNumber(Number(rows)), version: digits.slice(0, 8)})
                            : t('maintenance.index.dictionaryNone')
                          : t(stale.has(input) ? 'maintenance.inputs.changed' : 'maintenance.inputs.inIndex')}
                      </small>
                    </span>
                    <Link className="btn sm ghost" to={to}>
                      {t('maintenance.inputs.open')}
                      <Icon name="arrow" />
                    </Link>
                  </li>
                ))}
              </ol>
              <dl className="kv">
                <dt>{t('maintenance.index.built')}</dt>
                <dd>{index.built_at ? formatWhen(index.built_at, t) : '—'}</dd>
              </dl>
              <div className="mt-rebuild">
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
                <span className="note">{t('maintenance.index.rebuildNote')}</span>
              </div>
            </div>
          </section>
          <div className="mt-side">
            {sections.map((section) => (
              <SettingsCard key={section.id} settings={settings} section={section}>
                {section.id === 'cache' ? <SavedAnswers summary={summary} onCleared={readSummary} /> : null}
              </SettingsCard>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
