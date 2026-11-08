import {useEffect, useRef, useState, type ReactNode} from 'react';
import {useNavigate, useParams, useSearchParams} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {adminPath, dictionaryTablePath} from '@/components/admin/nav';
import {PageHead} from '@/components/admin/PageHead';
import {Skeleton} from '@/components/admin/Skeleton';
import {Fact} from '@/components/dictionary/Fact';
import {RunHistory} from '@/components/dictionary/RunHistory';
import {RunReport} from '@/components/dictionary/RunReport';
import {SourceCard} from '@/components/dictionary/SourceCard';
import {SyncProgress} from '@/components/dictionary/SyncProgress';
import {TableDrawer} from '@/components/dictionary/TableDrawer';
import {TableList} from '@/components/dictionary/TableList';
import {UpdateDrawer} from '@/components/dictionary/UpdateDrawer';
import {VersionList} from '@/components/dictionary/VersionList';
import {useIntl} from '@/contexts/IntlContext';
import {useDictionaryImport, useDownload, useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useDictionarySync} from '@/hooks/useDictionarySync';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {dictionaryStatus, versionDigits} from '@/lib/adminStatus';
import {formatDateTime, formatNumber} from '@/lib/format';
import {DictionaryService} from '@/services/dictionary';
import {DictionarySyncService} from '@/services/dictionarySync';
import type {DictionarySource, DictionaryVersion, SyncPreview, SyncRunSummary} from '@/types/dictionarySync';
import {confirmAction} from '@/lib/confirm';

const VIEWS = ['tables', 'runs', 'versions', 'source'] as const;
type View = (typeof VIEWS)[number];
/** The view's name in the address (`?gorunum=surumler`), so a reload or a shared link keeps it. */
const SLUGS: Record<View, string> = {tables: 'tablolar', runs: 'guncellemeler', versions: 'surumler', source: 'kaynak'};
const viewOfSlug = (slug: string | null): View | null => VIEWS.find((name) => SLUGS[name] === slug) ?? null;

/**
 * The "Sözlük" page (dictionary-management Requirement 13, 15; dictionary-sync Requirement 1, 2, 9,
 * 10, 12, 13): "Sözlüğü güncelle", the Excel import, the empty template and the export above the
 * version's facts, the live progress of a running run, and the tables, the update history, the kept
 * versions and the source connection, one at a time so that the page stays one screen. Without an
 * active version it points to the source and to the import. `/admin/sozluk/<key>` opens the
 * table's drawer.
 */
export default function DictionaryPage() {
  const {t} = useIntl();
  const navigate = useNavigate();
  const tableKey = useParams()['*'] ?? '';
  const {dictionary, tables, failure} = useDictionaryState();
  const {reportUnreachable} = useToast();
  const download = useDownload();
  const rebuild = useIndexRebuild();
  const [rebuilding, setRebuilding] = useState(false);
  const [params, setParams] = useSearchParams();
  const chosenView = viewOfSlug(params.get('gorunum'));
  const setChosenView = (name: View) => setParams({gorunum: SLUGS[name]}, {replace: true});
  const [source, setSource] = useState<DictionarySource | null>(null);
  const [sourceFailure, setSourceFailure] = useState<unknown>(null);
  const [focusRequest, setFocusRequest] = useState(0);
  const [report, setReport] = useState<{id: string; opened: number} | null>(null);
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewFailure, setPreviewFailure] = useState('');
  const [previewSince, setPreviewSince] = useState<number | null>(null);
  // The update window: open or not, and the run it followed when that run ended.
  const [updateOpen, setUpdateOpen] = useState(false);
  const [ended, setEnded] = useState<SyncRunSummary | null>(null);
  const windowOpen = useRef(false);
  useEffect(() => {
    windowOpen.current = updateOpen;
  }, [updateOpen]);
  const openReport = (id: string) => setReport((current) => ({id, opened: (current?.opened ?? 0) + 1}));
  const sync = useDictionarySync((run) => {
    // With the update window open, the window shows the end and offers the report.
    if (windowOpen.current) setEnded(run);
    else if (!tableKey) openReport(run.public_id);
  });
  const importWorkbook = useDictionaryImport(sync.settle);
  const pickWorkbook = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx';
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void importWorkbook(file);
    };
    input.click();
  };
  const label = t('admin.page.sozluk.label');
  const status = dictionaryStatus(dictionary);
  const active = status.active;

  useEffect(() => {
    let live = true;
    DictionarySyncService.source().then(
      (answer) => {
        if (live) setSource(answer);
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (live) setSourceFailure(error);
      },
    );
    return () => {
      live = false;
    };
  }, [reportUnreachable]);

  async function runRebuild() {
    setRebuilding(true);
    try {
      await rebuild();
    } finally {
      setRebuilding(false);
    }
  }

  async function restore(version: DictionaryVersion) {
    const question = t('dictionary.versions.restoreConfirm', {version: versionDigits(version.version)});
    if (await confirmAction(question, {action: t('dictionary.versions.restore')})) void sync.restore(version);
  }

  function connectSource() {
    setChosenView('source');
    setFocusRequest((count) => count + 1);
  }

  // The drawers keep their place while the page loads, so a deep link's drawer is not opened twice.
  const page = (body: ReactNode) => (
    <section className="page on" id="p-sozluk" aria-label={label}>
      <>{body}</>
      {tableKey ? <TableDrawer tableKey={tableKey} onClose={() => navigate(adminPath('sozluk'))} /> : null}
      {report ? (
        <RunReport key={report.opened} runId={report.id} onClose={() => setReport(null)} onChanged={(run) => void sync.adopt(run)} />
      ) : null}
    </section>
  );
  if (dictionary === null || (active && tables === null))
    return page(
      <>
        <PageHead title={label} />
        {failure ? <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(failure, t)})}</div> : <Skeleton />}
      </>,
    );

  const running = sync.running;

  async function openPreview() {
    // The window opens at once; the preview fills it when the server has read the source.
    setUpdateOpen(true);
    setEnded(null);
    setPreview(null);
    setPreviewFailure('');
    setPreviewSince(Date.now());
    setPreviewing(true);
    try {
      setPreview(await DictionarySyncService.preview());
    } catch (error) {
      reportUnreachable(error);
      setPreviewFailure(adminErrorText(error, t));
    } finally {
      setPreviewing(false);
    }
  }

  function openUpdate() {
    if (running) {
      setEnded(null);
      setUpdateOpen(true);
    } else void openPreview();
  }
  const waiting = sync.runs?.find((run) => run.status === 'pending_approval');
  const views = VIEWS.filter((name) => name !== 'tables' || active);
  const view = chosenView && views.includes(chosenView) ? chosenView : views[0];
  const configured = source?.configured === true;

  return page(
    <>
      <PageHead
        title={label}
        description={t('admin.page.sozluk.description')}
        actions={
          <>
            <button
              className="btn primary"
              type="button"
              disabled={!configured}
              title={source && !configured ? t('dictionary.sync.needsSource') : undefined}
              onClick={openUpdate}
            >
              <Icon name="refresh" />
              {t('dictionary.sync.button')}
            </button>
            <button
              className="btn"
              type="button"
              id="d-import"
              disabled={running !== null}
              title={t('dictionary.import.tip')}
              onClick={pickWorkbook}
            >
              <Icon name="import" />
              {t('dictionary.import.button')}
            </button>
            <button
              className="btn ghost"
              type="button"
              title={t('dictionary.template.tip')}
              onClick={() => void download(DictionaryService.template)}
            >
              {t('dictionary.template.button')}
            </button>
            {active ? (
              <button className="btn" type="button" onClick={() => void download(DictionaryService.exportWorkbook)}>
                <Icon name="export" />
                {t('dictionary.export.button')}
              </button>
            ) : null}
          </>
        }
      />
      {updateOpen ? (
        <UpdateDrawer
          preview={preview}
          previewFailure={previewFailure}
          previewSince={previewSince}
          run={running ?? ended}
          busy={previewing}
          onStart={() => {
            setPreview(null);
            void sync.start();
          }}
          onRetry={() => void openPreview()}
          onOpenReport={(id) => {
            setUpdateOpen(false);
            setEnded(null);
            openReport(id);
          }}
          onClose={() => {
            setUpdateOpen(false);
            setEnded(null);
          }}
        />
      ) : null}
      {running ? <SyncProgress run={running} onDetails={() => setUpdateOpen(true)} /> : null}
      {waiting ? (
        <div className="msg warn" id="d-waiting">
          {t('dictionary.sync.waiting')}{' '}
          <button className="btn sm" type="button" onClick={() => openReport(waiting.public_id)}>
            {t('dictionary.sync.openReport')}
          </button>
        </div>
      ) : null}
      {sync.failure ? <div className="msg bad">{t('dictionary.sync.listFailed', {reason: adminErrorText(sync.failure, t)})}</div> : null}
      {active ? (
        <section className="card">
          <div className="info">
            <Fact label={t('dictionary.info.tables')} value={formatNumber(active.object_count)} />
            <Fact label={t('dictionary.info.columns')} value={formatNumber(active.column_count)} />
            <Fact label={t('dictionary.info.source')} value={active.source_name} />
            <Fact label={t('dictionary.info.imported')} value={formatDateTime(active.imported_at)} />
            <Fact label={t('dictionary.info.version')} value={versionDigits(active.version)} title={active.version} />
            <div className="grow" />
            {status.state === 'ok' ? (
              <span className="pill ok">{t('dictionary.info.indexOk')}</span>
            ) : (
              <button className="btn sm primary" type="button" disabled={rebuilding} onClick={() => void runRebuild()}>
                {rebuilding ? (
                  t('maintenance.index.rebuilding')
                ) : (
                  <>
                    <Icon name="refresh" />
                    {t('dictionary.info.buildIndex')}
                  </>
                )}
              </button>
            )}
          </div>
          {active.warning_count ? <div className="msg warn">{t('dictionary.info.warnings', {count: active.warning_count})}</div> : null}
        </section>
      ) : (
        <section className="card" id="d-empty">
          <h2>{t('dictionary.empty.title')}</h2>
          <p className="intro">{t('dictionary.empty.body')}</p>
          <div className="acts" style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
            <button className="btn primary" type="button" onClick={connectSource}>
              <Icon name="db" />
              {t('dictionary.empty.connect')}
            </button>
            <button className="btn" type="button" disabled={running !== null} onClick={pickWorkbook}>
              <Icon name="import" />
              {t('dictionary.import.button')}
            </button>
          </div>
        </section>
      )}
      <div className="card-h">
        <div className="seg" role="group" aria-label={t('dictionary.view.label')}>
          {views.map((name) => (
            <button key={name} type="button" aria-pressed={view === name} onClick={() => setChosenView(name)}>
              {t(`dictionary.view.${name}`)}
            </button>
          ))}
        </div>
      </div>
      {view === 'tables' ? <TableList tables={tables ?? []} onOpen={(key) => navigate(dictionaryTablePath(key))} /> : null}
      {view === 'runs' ? (
        <div className="fill scroll">
          <RunHistory
            runs={sync.runs}
            total={sync.runsTotal}
            page={sync.runsPage}
            onPage={sync.showRuns}
            onOpen={(run) => openReport(run.public_id)}
          />
        </div>
      ) : null}
      {view === 'versions' ? (
        <div className="fill scroll">
          <VersionList versions={sync.versions} busy={running !== null} onRestore={(version) => void restore(version)} onReport={openReport} />
        </div>
      ) : null}
      {/* Stays mounted, so a half-typed connection survives a look at another view. */}
      <div className="fill scroll" hidden={view !== 'source'}>
        {source ? (
          <SourceCard source={source} focusRequest={focusRequest} onSaved={setSource} />
        ) : sourceFailure ? (
          <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(sourceFailure, t)})}</div>
        ) : (
          <Skeleton />
        )}
      </div>
    </>,
  );
}
