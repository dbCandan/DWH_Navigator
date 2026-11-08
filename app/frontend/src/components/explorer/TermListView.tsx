import {memo, useEffect, useState, type CSSProperties} from 'react';
import {AnswerView} from '@/components/explorer/AnswerView';
import {useIntl} from '@/contexts/IntlContext';
import {pct, verdictClass} from '@/lib/answerText';
import {config} from '@/lib/config';
import {explorerErrorText} from '@/lib/explorerErrors';
import {listDuration, unavailableCount} from '@/lib/termLists';
import {TermListService} from '@/services/termLists';
import type {AnalysisAnswer} from '@/types/analysis';
import type {TermList, TermRow} from '@/types/termLists';

/*
 * The term list on the main screen (list-search Requirement 17; index.html Bulk): the progress
 * head, the bar, the reading notes and a row per term that opens the term's answer under it. Only
 * a row whose state changed is drawn again, so an opened answer stays in place while the list runs.
 */

/** A term's state word and colour class while it has no answer (index.html Bulk.STATE). */
const STATE: Record<Exclude<TermRow['state'], 'answered'>, [string, string]> = {
  queued: ['list.state.queued', 'wait'],
  running: ['list.state.running', 'run'],
  error: ['list.state.error', 'err'],
  stopped: ['list.state.stopped', 'wait'],
};

interface Handlers {
  /** "↻ Yeniden analiz et" in a term's answer: the term as a new single question. */
  onRedo: (query: string) => void;
  openTable?: (key: string) => void;
  hasTable?: (key: string) => boolean;
  /** Every table of the dictionary, for the names in the answers' prose. */
  catalog?: readonly {key: string; name: string}[];
}

/** A term's answer under its row: read once when opened (Requirement 12). */
function TermDetail({listId, position, onRedo, openTable, hasTable, catalog}: Handlers & {listId: string; position: number}) {
  const {t} = useIntl();
  const [answer, setAnswer] = useState<AnalysisAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    TermListService.item(listId, position).then(
      (got) => {
        if (live) setAnswer(got);
      },
      (failure: unknown) => {
        if (live) setError(explorerErrorText(failure, t));
      },
    );
    return () => {
      live = false;
    };
  }, [listId, position, t]);
  return (
    <div className="li-detail">
      {error !== null ? (
        <div className="error">{error}</div>
      ) : answer === null ? (
        <p className="faint">{t('list.loading')}</p>
      ) : (
        <AnswerView
          answer={answer}
          reportHref={`${config.apiPrefix}/term-lists/${encodeURIComponent(listId)}/items/${position}/report`}
          onReport={() => void TermListService.itemReport(listId, position).catch(() => undefined)}
          onRedo={() => onRedo(answer.query)}
          openTable={openTable}
          hasTable={hasTable}
          catalog={catalog}
        />
      )}
    </div>
  );
}

interface RowProps extends Handlers {
  listId: string;
  item: TermRow;
  open: boolean;
  onToggle: (position: number) => void;
}

/** A term's row; drawn again only when its own state changes. */
const TermItem = memo(function TermItem({listId, item: it, open, onToggle, ...handlers}: RowProps) {
  const {t} = useIntl();
  const done = it.state === 'answered';
  const [wordKey, cls] = it.state === 'answered' ? ['', ''] : STATE[it.state];
  const word = done ? it.verdict : t(wordKey);
  return (
    <li>
      <button
        className="li-row"
        type="button"
        aria-expanded={done ? open : undefined}
        onClick={done ? () => onToggle(it.position) : undefined}
      >
        <span className="li-n">{it.position}</span>
        <span className="li-term">
          {it.term}
          {done && it.flow === 'reused' ? (
            <span className="li-flow reused" title={t('list.flow.reusedTip')}>
              {t('list.flow.reused')}
            </span>
          ) : done && it.flow !== 'analyst' ? (
            <span className="li-flow" title={t('list.flow.unavailableTip')}>
              {t('list.flow.unavailable')}
            </span>
          ) : null}
          {it.best ? (
            <span className="li-best">
              {it.best.name}
              {' · '}
              <b className={'lc-' + it.best.level}>{'%' + pct(it.best.score)}</b>
            </span>
          ) : null}
          {done && it.missing.length ? <span className="li-miss">{t('list.missing', {items: it.missing.join(', ')})}</span> : null}
          {it.state === 'error' ? <span className="li-best">{it.summary}</span> : null}
        </span>
        <span className={`st ${cls} ${done ? verdictClass(it.verdict) : ''}`}>{word}</span>
        <span className="li-ms">{it.elapsed_ms ? listDuration(it.elapsed_ms, t) : ''}</span>
      </button>
      {open ? <TermDetail listId={listId} position={it.position} {...handlers} /> : null}
    </li>
  );
}, sameRow);

/** The source's row signature: state, verdict, flow, time, best table and summary. */
function sameRow(a: RowProps, b: RowProps): boolean {
  const x = a.item;
  const y = b.item;
  return (
    a.listId === b.listId &&
    a.open === b.open &&
    a.onToggle === b.onToggle &&
    a.onRedo === b.onRedo &&
    a.openTable === b.openTable &&
    a.hasTable === b.hasTable &&
    a.catalog === b.catalog &&
    x.state === y.state &&
    x.verdict === y.verdict &&
    x.flow === y.flow &&
    x.elapsed_ms === y.elapsed_ms &&
    x.summary === y.summary &&
    JSON.stringify(x.best) === JSON.stringify(y.best)
  );
}

interface Props extends Handlers {
  list: TermList;
  /** The terms whose answer is open; kept by the page across the pill (index.html Bulk.open). */
  opened: ReadonlySet<number>;
  onToggle: (position: number) => void;
  onStop: () => Promise<void>;
  /** Resolves with the refusal, if any; it is shown in the browser's alert. */
  onResume: () => Promise<unknown>;
}

/** The whole list view (index.html Bulk.show/render). */
export function TermListView({list, opened, onToggle: toggle, onStop, onResume, onRedo, openTable, hasTable, catalog}: Props) {
  const {t} = useIntl();
  const [stopping, setStopping] = useState(false);
  const [resuming, setResuming] = useState(false);
  const running = list.status === 'running';
  const frac = list.total ? list.done / list.total : 0;
  const progress = running
    ? t('list.progress.running', {done: list.done, total: list.total}) +
      (list.eta_ms ? t('list.progress.eta', {eta: listDuration(list.eta_ms, t)}) : '')
    : list.status === 'cancelled'
      ? t('list.progress.cancelled', {done: list.done, total: list.total})
      : list.status === 'interrupted'
        ? t('list.progress.interrupted', {done: list.done, total: list.total})
        : t('list.progress.completed', {total: list.total, elapsed: listDuration(list.elapsed_ms, t)});
  const canResume = !running && (list.status === 'cancelled' || list.status === 'interrupted') && list.done < list.total;
  const unavailable = unavailableCount(list);

  async function stop() {
    setStopping(true);
    await onStop();
    setStopping(false);
  }

  async function resume() {
    setResuming(true);
    const refused = await onResume();
    setResuming(false);
    if (refused !== null) window.alert(explorerErrorText(refused, t));
  }

  return (
    <section className="list">
      <div>
        <div className="list-head">
          <div className="ttl">
            <h2>{list.name}</h2>
            <div className="sub">
              {progress}
              {list.header ? <span className="faint">{t('list.header', {header: list.header})}</span> : null}
            </div>
          </div>
          {running ? (
            <button className="ghost" type="button" disabled={stopping} onClick={() => void stop()}>
              {t('list.stop')}
            </button>
          ) : null}
          {canResume ? (
            <button className="ghost" type="button" title={t('list.resumeTip')} disabled={resuming} onClick={() => void resume()}>
              {t('list.resume')}
            </button>
          ) : null}
          {list.done ? (
            <a
              className="ghost"
              href={`${config.apiPrefix}/term-lists/${encodeURIComponent(list.id)}/report`}
              download=""
              onClick={(event) => {
                event.preventDefault();
                void TermListService.report(list.id).catch(() => undefined);
              }}
            >
              {running ? t('list.reportSoFar') : t('list.report')}
            </a>
          ) : null}
        </div>
        <div className={'list-bar' + (running ? ' live' : '')}>
          <i style={{width: `${Math.max(2, frac * 100)}%`} as CSSProperties} />
        </div>
        {list.notes.length ? (
          <div className="list-notes">
            {list.notes.map((note, i) => (
              <div key={i}>{'ℹ ' + note}</div>
            ))}
          </div>
        ) : null}
        {unavailable ? <div className="answer-fallback">{t('list.unavailable', {count: unavailable})}</div> : null}
      </div>
      <ol className="list-items">
        {list.items.map((item) => (
          <TermItem
            key={item.position}
            listId={list.id}
            item={item}
            open={opened.has(item.position)}
            onToggle={toggle}
            onRedo={onRedo}
            openTable={openTable}
            hasTable={hasTable}
            catalog={catalog}
          />
        ))}
      </ol>
    </section>
  );
}

/** "“{name}” yüklenemedi.": the refusal and the one accepted layout as a picture (index.html formatHelp). */
export function ListFormatHelp({name, message}: {name: string; message: string}) {
  const {t} = useIntl();
  const row = (n: number, value: string, cls = '') => (
    <tr>
      <th>{n}</th>
      <td className={cls}>{value}</td>
      <td className="off" />
    </tr>
  );
  return (
    <section className="xl-help">
      <div className="error">
        <b>{t('list.help.failed', {name})}</b>
        {message.replace(/ Beklenen biçim:.*$/, '')}
      </div>
      <div className="xl-ex">
        <table>
          <thead>
            <tr>
              <th />
              <th>A</th>
              <th>B</th>
            </tr>
          </thead>
          <tbody>
            {row(1, t('list.help.header'), 'hd')}
            {row(2, t('list.help.example1'))}
            {row(3, t('list.help.example2'))}
            {row(4, t('list.help.example3'))}
          </tbody>
        </table>
        <ul>
          <li>
            <b>{t('list.help.ruleColumn')}</b>
            {t('list.help.ruleColumnText')}
          </li>
          <li>
            <b>{t('list.help.ruleHeader')}</b>
            {t('list.help.ruleHeaderText')}
          </li>
          <li>
            <b>{t('list.help.ruleRows')}</b>
            {t('list.help.ruleRowsText')}
          </li>
          <li>
            <b>{t('list.help.ruleSheet')}</b>
            {t('list.help.ruleSheetText')}
          </li>
        </ul>
      </div>
    </section>
  );
}
