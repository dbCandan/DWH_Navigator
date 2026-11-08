import {useCallback, useEffect, useRef, useState} from 'react';
import {useLocation, useNavigate, useParams} from 'react-router';
import {Drawer} from '@/components/admin/Drawer';
import {Icon} from '@/components/admin/Icon';
import {adminPath, analysisPath, type RecordsDrawerRequest} from '@/components/admin/nav';
import {PageHead} from '@/components/admin/PageHead';
import {PerformanceDrawer} from '@/components/admin/PerformanceDrawer';
import {RecordDetailBody} from '@/components/admin/RecordDetailBody';
import {FlowChip, KpiTiles, Meter, VerdictBadge} from '@/components/admin/RecordParts';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {FLOWS, PERIODS, recordKpis, tableName} from '@/lib/analysisRecords';
import {formatDateTime, formatDuration, formatNumber, formatWhen} from '@/lib/format';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {SavedAnswersService} from '@/services/savedAnswers';
import type {Asker, Flow, Period, RecordDetail, RecordFilters, RecordRow, RecordSummary} from '@/types/records';
import {confirmAction} from '@/lib/confirm';

/** The live refresh period (Requirement 17). */
const LIVE_MS = 15000;
/** The search box sends its text this long after the typing stops (Requirement 16). */
const TYPING_MS = 300;

interface Loaded {
  /** The filters the rows were read with. */
  key: string;
  rows: RecordRow[];
  total: number;
  /** The list's `snapshot_at`: "Daha fazla" and the deletion use it as `until`. */
  until: string;
  pages: number;
}

function requestOf(state: unknown): RecordsDrawerRequest | null {
  return (state as {open?: unknown} | null)?.open === 'performance' ? 'performance' : null;
}

const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement && /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName);

/**
 * The "Analizler" page (analysis-records Requirement 16-22; admin.html Analyses): the filters,
 * the four indicators over the filter, the list 150 rows at a time with "Daha fazla", the live
 * refresh, the record drawer at `/admin/analizler/<public_id>` with ↑/↓ between loaded rows, the
 * "Performans" drawer and "Temizle…".
 */
export default function AnalysesPage() {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const openId = useParams().analysisId ?? '';
  const [period, setPeriod] = useState<Period>('7d');
  const [flow, setFlow] = useState<Flow | ''>('');
  const [askedBy, setAskedBy] = useState('');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [live, setLive] = useState(true);
  const [loadedRaw, setLoaded] = useState<Loaded | null>(null);
  const [summaryRead, setSummaryRead] = useState<{key: string; value: RecordSummary} | null>(null);
  const [askers, setAskers] = useState<Asker[] | null>(null);
  const [failureRead, setFailureRead] = useState<{key: string; error: unknown} | null>(null);
  const [busy, setBusy] = useState(false);
  const [perfOpen, setPerfOpen] = useState(false);
  const [handled, setHandled] = useState<string | null>(null);
  const [records, setRecords] = useState<Record<string, RecordDetail>>({});
  const [detailFailure, setDetailFailure] = useState<{id: string; error: unknown} | null>(null);
  const loadedRef = useRef<Loaded | null>(null);
  const reads = useRef(0);
  const label = t('admin.page.analizler.label');
  const filters: RecordFilters = {period, flow, asked_by: askedBy, q};
  const filterKey = JSON.stringify(filters);
  const shownList = loadedRaw?.key === filterKey ? loadedRaw : null;
  const summary = summaryRead?.key === filterKey ? summaryRead.value : null;
  const failure = failureRead?.key === filterKey ? failureRead.error : null;

  // "Performans ayrıntıları" in the command palette opens the drawer here.
  const request = requestOf(location.state);
  if (request && handled !== location.key) {
    setHandled(location.key);
    setPerfOpen(true);
  }
  useEffect(() => {
    if (request) navigate(location.pathname, {replace: true, state: null});
  }, [request, location.pathname, navigate]);

  // The search goes out 300 ms after the typing stops.
  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), TYPING_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  /**
   * Read the list, its summary and the askers with a new `until`. `keep` reads as many pages as
   * are shown (the live refresh and "Yenile"), else the first page only (a new filter).
   */
  const load = useCallback(
    async (keep: boolean) => {
      const current: RecordFilters = JSON.parse(filterKey) as RecordFilters;
      const mine = ++reads.current;
      const pages = keep && loadedRef.current?.key === filterKey ? Math.max(1, loadedRef.current.pages) : 1;
      try {
        const first = await AnalysisRecordsService.list(current, 1);
        const until = first.snapshot_at;
        const [rest, summaryAnswer, askersAnswer] = await Promise.all([
          Promise.all(Array.from({length: pages - 1}, (_, i) => AnalysisRecordsService.list(current, i + 2, until))),
          AnalysisRecordsService.summary(current, until),
          AnalysisRecordsService.askers(),
        ]);
        if (mine !== reads.current) return;
        const rows = [first, ...rest].flatMap((page) => page.items);
        loadedRef.current = {key: filterKey, rows, total: first.total, until, pages};
        setLoaded(loadedRef.current);
        setSummaryRead({key: filterKey, value: summaryAnswer});
        setAskers(askersAnswer.items);
        setFailureRead(null);
      } catch (error) {
        if (mine !== reads.current) return;
        reportUnreachable(error);
        setFailureRead({key: filterKey, error});
      }
    },
    [filterKey, reportUnreachable],
  );

  // A new filter loads the list from the start with a new `until`.
  useEffect(() => {
    void load(false);
  }, [load]);

  async function refresh() {
    setBusy(true);
    try {
      await load(true);
    } finally {
      setBusy(false);
    }
  }

  const drawerOpen = Boolean(openId) || perfOpen;
  // Live: every 15 s while the switch is on, the tab is visible and no drawer is open.
  useEffect(() => {
    if (!live || drawerOpen) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') void load(true);
    }, LIVE_MS);
    return () => window.clearInterval(timer);
  }, [live, drawerOpen, load]);

  async function more() {
    const current = loadedRef.current;
    if (!current || current.key !== filterKey) return;
    const mine = reads.current;
    try {
      const page = await AnalysisRecordsService.list(filters, current.pages + 1, current.until);
      if (mine !== reads.current) return;
      loadedRef.current = {...current, rows: [...current.rows, ...page.items], pages: current.pages + 1};
      setLoaded(loadedRef.current);
    } catch (error) {
      reportUnreachable(error);
      setFailureRead({key: current.key, error});
    }
  }

  // The record's drawer follows the address; a record read once is kept.
  const known = Boolean(openId && records[openId]);
  useEffect(() => {
    if (!openId || known) return;
    let current = true;
    AnalysisRecordsService.detail(openId).then(
      (record) => {
        if (current) setRecords((held) => ({...held, [openId]: record}));
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (current) setDetailFailure({id: openId, error});
      },
    );
    return () => {
      current = false;
    };
  }, [openId, known, reportUnreachable]);

  // ↓ and ↑ open the next and previous loaded row while the record's drawer is open.
  const rows = shownList?.rows;
  useEffect(() => {
    if (!openId || !rows) return;
    const step = (event: KeyboardEvent) => {
      if ((event.key !== 'ArrowDown' && event.key !== 'ArrowUp') || typing(event.target)) return;
      if (document.querySelector('.palette')) return;
      event.preventDefault();
      const at = rows.findIndex((row) => row.public_id === openId);
      const next = rows[at + (event.key === 'ArrowDown' ? 1 : -1)];
      if (at >= 0 && next) navigate(analysisPath(next.public_id));
    };
    window.addEventListener('keydown', step);
    return () => window.removeEventListener('keydown', step);
  }, [openId, rows, navigate]);

  const periodName = t(`records.periodName.${period}`);

  async function clear() {
    const current = shownList;
    if (!current) return;
    if (!current.total) {
      toast(t('records.clear.nothing'), [t('records.clear.nothingLine')]);
      return;
    }
    const filtered = Boolean(flow || askedBy || q);
    const all = period === 'all' && !filtered;
    const count = formatNumber(current.total);
    const question = all
      ? t('records.clear.confirmAll', {count})
      : t(filtered ? 'records.clear.confirmFiltered' : 'records.clear.confirmPeriod', {
          count,
          period: periodName.toLocaleLowerCase('tr-TR'),
        });
    if (!(await confirmAction(question, {action: t('records.clear.confirmAction'), danger: true}))) return;
    setBusy(true);
    try {
      const answer = await AnalysisRecordsService.remove(current.until, all ? {all: true} : {filters});
      setRecords({});
      toast(t('records.clear.done'), [
        t('records.clear.doneLine', {deleted: formatNumber(answer.deleted_count), remaining: formatNumber(answer.remaining_count)}),
      ]);
      if (
        await confirmAction(t('records.clear.answersConfirm'), {
          action: t('records.clear.answersAction'),
          cancel: t('records.clear.answersKeep'),
          danger: true,
        })
      ) {
        const removed = await SavedAnswersService.clear();
        toast(t('maintenance.answers.cleared'), [t('maintenance.answers.clearedLine', {count: formatNumber(removed.removed)})]);
      }
    } catch (error) {
      reportUnreachable(error);
      toast(t('records.clear.failed'), [adminErrorText(error, t)], true);
    } finally {
      await load(false);
      setBusy(false);
    }
  }

  const listBox = (() => {
    if (failure) return <div className="msg bad">{t('records.failed', {reason: adminErrorText(failure, t)})}</div>;
    const loaded = shownList;
    if (!loaded) return <Skeleton />;
    if (!loaded.total)
      return <p className="empty">{askers && askers.length === 0 ? t('records.empty.none') : t('records.empty.filter')}</p>;
    const left = loaded.total - loaded.rows.length;
    const maxDuration = Math.max(...loaded.rows.map((row) => row.duration_ms ?? 0));
    return (
      <>
        <table className="t">
          <thead>
            <tr>
              <th>{t('records.col.when')}</th>
              <th>{t('records.col.question')}</th>
              <th>{t('records.col.flow')}</th>
              <th>{t('records.col.asker')}</th>
              <th className="r">{t('records.col.duration')}</th>
            </tr>
          </thead>
          <tbody>
            {loaded.rows.map((row) => {
              const first = row.table_keys[0];
              const open = () => navigate(analysisPath(row.public_id));
              return (
                <tr
                  key={row.public_id}
                  className={'click' + (openId === row.public_id ? ' sel' : '')}
                  tabIndex={0}
                  data-id={row.public_id}
                  onClick={open}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      open();
                    }
                  }}
                >
                  <td className="when">{formatWhen(row.asked_at, t)}</td>
                  <td className="qq">
                    <div className="q">
                      {row.query}
                      {row.origin === 'list' && row.list_file_name ? (
                        <span className="orig" title={t('records.originTip')}>
                          {t('records.origin', {file: row.list_file_name, position: row.list_position ?? ''})}
                        </span>
                      ) : null}
                    </div>
                    <div className="a">
                      <VerdictBadge verdict={row.verdict} flow={row.flow} />
                      {first
                        ? row.table_keys.length > 1
                          ? t('records.moreTables', {name: tableName(first), count: row.table_keys.length - 1})
                          : tableName(first)
                        : row.unavailable_reason || row.error?.message || ''}
                    </div>
                  </td>
                  <td>
                    <FlowChip flow={row.flow} />
                  </td>
                  <td className="asker" title={row.asked_by.display_name}>
                    {row.asked_by.display_name}
                  </td>
                  <td className="dur metered">
                    {formatDuration(row.duration_ms, t)}
                    <Meter value={row.duration_ms ?? 0} max={maxDuration} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {left > 0 ? (
          <div className="more">
            <button className="btn" type="button" onClick={() => void more()}>
              {t('records.more', {count: formatNumber(left)})}
            </button>
          </div>
        ) : null}
      </>
    );
  })();

  const record = openId ? (records[openId] ?? null) : null;
  const recordFailure = detailFailure?.id === openId ? detailFailure.error : null;
  return (
    <section className="page on" id="p-analizler" aria-label={label}>
      <PageHead
        title={label}
        description={t('admin.page.analizler.description')}
        actions={
          <>
            <button className="btn" type="button" disabled={busy} onClick={() => void refresh()}>
              <Icon name="refresh" />
              {t('records.refresh')}
            </button>
            <button className="btn" type="button" onClick={() => setPerfOpen(true)}>
              <Icon name="gauge" />
              {t('records.performance')}
            </button>
            <button className="btn danger" type="button" disabled={busy} onClick={() => void clear()}>
              {t('records.clear')}
            </button>
          </>
        }
      />
      <div className="toolbar">
        <div className="seg" role="group" aria-label={t('records.period.label')}>
          {PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={value === period}
              onClick={() => setPeriod(value)}
            >
              {t(`records.period.${value}`)}
            </button>
          ))}
        </div>
        <select
          aria-label={t('records.flowFilter.label')}
          value={flow}
          onChange={(event) => setFlow(event.target.value as Flow | '')}
        >
          <option value="">{t('records.flowFilter.all')}</option>
          {FLOWS.map((value) => (
            <option value={value} key={value}>
              {t(`records.flow.${value}`)}
            </option>
          ))}
        </select>
        <select
          id="a-user"
          aria-label={t('records.asker.label')}
          value={askedBy}
          onChange={(event) => setAskedBy(event.target.value)}
        >
          <option value="">{t('records.asker.all')}</option>
          {(askers ?? []).map((asker) => (
            <option value={asker.public_id} key={asker.public_id}>
              {asker.display_name}
            </option>
          ))}
        </select>
        <input
          type="search"
          id="a-text"
          placeholder={t('records.search.placeholder')}
          aria-label={t('records.search.label')}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <label className="live" title={t('records.live.tip')}>
          <span className="switch">
            <input type="checkbox" checked={live} onChange={(event) => setLive(event.target.checked)} />
            <span />
          </span>
          {t('records.live.label')}
        </label>
      </div>
      <div className="kpis a" id="a-kpis">
        {summary ? <KpiTiles kpis={recordKpis(summary, t)} /> : null}
      </div>
      <section className="card grow">
        <div className="card-h">
          <h2 id="a-title">
            {shownList
              ? t('records.list.title', {period: periodName, count: formatNumber(shownList.total)})
              : t('records.list.titleLoading')}
          </h2>
        </div>
        <div className="list-box" id="a-list">
          {listBox}
        </div>
      </section>
      {openId ? (
        <Drawer
          wide
          title={record ? record.query : t('records.detail.title')}
          sub={
            record
              ? t('records.detail.sub', {
                  at: formatDateTime(record.asked_at),
                  asker: record.asked_by.display_name,
                  duration: formatDuration(record.duration_ms, t),
                })
              : recordFailure
                ? undefined
                : t('admin.loading')
          }
          onClose={() => navigate(adminPath('analizler'))}
        >
          {record ? (
            <RecordDetailBody record={record} />
          ) : recordFailure ? (
            <div className="msg bad">{adminErrorText(recordFailure, t)}</div>
          ) : (
            <Skeleton />
          )}
        </Drawer>
      ) : perfOpen ? (
        <PerformanceDrawer
          period={periodName}
          summary={summary}
          onPick={(publicId) => {
            setPerfOpen(false);
            setAskedBy(publicId);
          }}
          onClose={() => setPerfOpen(false)}
        />
      ) : null}
    </section>
  );
}
