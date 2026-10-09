import {useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type MouseEvent, type ReactNode} from 'react';
import {Breakable} from '@/components/explorer/Breakable';
import {useIntl} from '@/contexts/IntlContext';
import {useRootClass} from '@/hooks/useSurface';
import type {Star} from '@/lib/cosmos/layout';
import {explorerErrorText} from '@/lib/explorerErrors';
import {fold} from '@/lib/fold';
import {trapTab} from '@/lib/focusTrap';
import {ExplorerService} from '@/services/explorer';
import type {TableColumn, TableDetail} from '@/types/explorer';

/** The colour of a table without a star (index.html Dossier.open). */
const DEFAULT_HUE = 190;
const SKELETON_ROWS = 5;
const SIBLINGS = 14;
const SHORT_DESCRIPTION = 140;
const COPY_NOTE_MS = 1400;

type Filter = 'all' | 'key' | 'pii';
const FILTERS: readonly Filter[] = ['all', 'key', 'pii'];

/** The table that is open: its key, its star when it has one, and an opening count. */
export interface OpenTable {
  key: string;
  star: Star | null;
  /** Grows with every opening: a new star replays the entrance. */
  seq: number;
}

interface Props {
  table: OpenTable | null;
  /** Another table from the "Aynı kümede" buttons. */
  onOpen: (key: string) => void;
  onClose: () => void;
}

/** The matched parts in <mark>; folding keeps one character per character for Turkish text. */
function marked(text: string, term: string): ReactNode {
  const folded = fold(text);
  if (!term || folded.length !== text.length) return text;
  const out: ReactNode[] = [];
  let i = 0;
  let j: number;
  while ((j = folded.indexOf(term, i)) !== -1) {
    out.push(text.slice(i, j), <mark key={j}>{text.slice(j, j + term.length)}</mark>);
    i = j + term.length;
  }
  out.push(text.slice(i));
  return out;
}

function ColumnRow({column, index, term, isKey}: {column: TableColumn; index: number; term: string; isKey: boolean}) {
  const {t} = useIntl();
  const [open, setOpen] = useState(false);
  function toggle(event: MouseEvent<HTMLDivElement>) {
    event.stopPropagation();
    // A mouse click while text is selected keeps the row as it is; a key press always toggles.
    if (event.detail !== 0 && getSelection()?.toString()) return;
    setOpen(!open);
  }
  const cls = 'ds-col' + (isKey ? ' is-key' : '') + (column.pii ? ' is-pii' : '') + (open ? ' open' : '');
  return (
    <div className={cls} style={{'--i': index} as CSSProperties} onClick={toggle}>
      <button className="ds-ctop" type="button" aria-expanded={open}>
        <span className="ds-cname">{marked(column.column, term)}</span>
        {isKey ? (
          <span className="ds-badge key" title={t('dossier.keyTip')}>
            {t('dossier.keyBadge')}
          </span>
        ) : null}
        {column.pii ? (
          <span className="ds-badge pii" title={t('dossier.piiTip')}>
            {t('dossier.piiBadge')}
          </span>
        ) : null}
      </button>
      {column.description ? (
        <p className="ds-desc">{marked(column.description, term)}</p>
      ) : (
        <p className="ds-desc none">{t('dossier.noDescription')}</p>
      )}
      <div className="ds-more">
        {column.synonyms.length ? (
          <div className="ds-syn">
            <b>{t('dossier.synonyms')}</b>
            {marked(column.synonyms.join(', '), term)}
          </div>
        ) : null}
        {!column.synonyms.length && column.description.length < SHORT_DESCRIPTION ? (
          <div className="faint">{t('dossier.noNote')}</div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({cls, n, label, i}: {cls: string; n: number; label: string; i: number}) {
  return (
    <div className={`ds-stat ${cls}${n ? '' : ' zero'}`} style={{'--i': i} as CSSProperties}>
      <b>{n.toLocaleString('tr-TR')}</b>
      <span>{label}</span>
    </div>
  );
}

/**
 * The table file (dictionary-explorer Requirement 11-13; index.html Dossier): the panel that
 * opens from the right with every column of a table, its join keys and KVKK marks, a column
 * search, filters and the other tables of its cluster. It locks the page behind it: the focus
 * goes to "Kapat", stays in the panel, Esc closes and the focus goes back to the opener.
 */
export function Dossier({table, onOpen, onClose}: Props) {
  const {t} = useIntl();
  const panel = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const searchField = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  // What the panel shows belongs to one opening (its count): a new opening starts with no
  // columns, an empty search and "Tümü", and a late answer for an earlier one is dropped.
  const [loaded, setLoaded] = useState<{seq: number; detail: TableDetail | null; error: string | null} | null>(null);
  const [search, setSearch] = useState<{seq: number; query: string; filter: Filter} | null>(null);
  const [copyNote, setCopyNote] = useState<string | null>(null);
  // The last table stays on the panel while it slides out (the source only hides the panel).
  const [held, setHeld] = useState<OpenTable | null>(table);
  if (table !== null && table !== held) setHeld(table);
  // The cluster row hides once a table without neighbours has loaded, until the next one has.
  const [footHidden, setFootHidden] = useState(false);
  const open = table !== null;
  useRootClass('dossier-open', open);
  const latest = useRef({onClose});
  useEffect(() => {
    latest.current = {onClose};
  });

  const key = table?.key ?? null;
  const seq = table?.seq ?? 0;
  const shownTable = table ?? held;
  const shownKey = shownTable?.key ?? null;
  const shownSeq = shownTable?.seq ?? 0;
  const star = shownTable?.star ?? null;
  const query = search?.seq === shownSeq ? search.query : '';
  const filter = search?.seq === shownSeq ? search.filter : 'all';
  const setQuery = (value: string) => setSearch({seq: shownSeq, query: value, filter});
  const setFilter = (value: Filter) => setSearch({seq: shownSeq, query, filter: value});

  // A new table: replay the entrance, clear the search and the filter, read its columns; a late
  // answer for an earlier table is dropped (Requirement 12).
  useLayoutEffect(() => {
    const el = panel.current;
    if (key === null || !el) return;
    if (!el.classList.contains('on')) {
      const active = document.activeElement;
      returnFocus.current = active instanceof HTMLElement && !el.contains(active) ? active : null;
    }
    el.classList.remove('on');
    void el.offsetWidth;
    el.classList.add('on');
    closeButton.current?.focus({preventScroll: true});
  }, [key, seq]);

  const node = table?.star ?? null;
  useEffect(() => {
    if (key === null) return;
    let live = true;
    ExplorerService.table(key).then(
      (detail) => {
        if (!live) return;
        setLoaded({seq, detail, error: null});
        setFootHidden(!node || node.g.members.length < 2);
      },
      (error: unknown) => {
        if (live) setLoaded({seq, detail: null, error: explorerErrorText(error, t)});
      },
    );
    return () => {
      live = false;
    };
  }, [key, seq, node, t]);

  // Closing gives the focus back to the control that opened the file.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      return;
    }
    if (!wasOpen.current) return;
    wasOpen.current = false;
    panel.current?.classList.remove('on');
    const back = returnFocus.current;
    returnFocus.current = null;
    if (back?.isConnected) back.focus({preventScroll: true});
  }, [open]);

  // Esc closes and "/" goes to the column search, before the page's own keys (index.html: capture).
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopImmediatePropagation();
        latest.current.onClose();
      } else if (event.key === '/' && document.activeElement !== searchField.current) {
        event.preventDefault();
        event.stopImmediatePropagation();
        searchField.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [open]);

  useEffect(() => {
    if (copyNote === null) return;
    const timer = window.setTimeout(() => setCopyNote(null), COPY_NOTE_MS);
    return () => window.clearTimeout(timer);
  }, [copyNote]);

  const detail = loaded?.seq === shownSeq ? loaded.detail : null;
  const error = loaded?.seq === shownSeq ? loaded.error : null;
  const keys = new Set(detail?.join_keys ?? []);
  const kind = (c: TableColumn): Record<Filter, boolean> => ({all: true, key: keys.has(c.column), pii: c.pii});
  const term = fold(query.trim());
  const columns = detail?.columns ?? [];
  const shown = columns.filter(
    (c) => kind(c)[filter] && (!term || fold(`${c.column} ${c.description} ${c.synonyms.join(' ')}`).includes(term)),
  );

  useLayoutEffect(() => {
    if (list.current) list.current.scrollTop = 0;
  }, [query, filter, detail]);

  const siblings = star && detail
    ? star.g.members
        .filter((m) => m !== star)
        .sort((a, b) => b.columns - a.columns)
        .slice(0, SIBLINGS)
    : [];
  const kicker = detail?.groups.length ? detail.groups.join(' · ') : star ? star.group : t('dossier.kicker');
  const name = star ? star.name : ((shownKey ?? '').split('.').pop() ?? '');

  async function copy() {
    try {
      await navigator.clipboard.writeText(shownKey ?? '');
      setCopyNote(t('dossier.copied'));
    } catch {
      setCopyNote(t('dossier.copyFailed'));
    }
  }

  const filterName: Record<Filter, string> = {all: t('dossier.filterAll'), key: t('dossier.filterKey'), pii: t('dossier.filterPii')};

  return (
    <aside
      className="dossier"
      id="dossier"
      role="dialog"
      aria-modal={open ? true : undefined}
      aria-labelledby="ds-name"
      aria-hidden={!open}
      ref={panel}
      style={{'--hue': star ? star.hue : DEFAULT_HUE} as CSSProperties}
      onKeyDown={(event) => trapTab(event, panel.current)}
    >
      <header className="ds-head">
        <div className="ds-planet" aria-hidden="true" />
        <div className="ds-title">
          <div className="ds-kicker" id="ds-kicker">
            {shownTable ? kicker : null}
          </div>
          <h2 id="ds-name">{shownTable ? <Breakable name={name} /> : null}</h2>
          <div className="ds-path">
            <code id="ds-path" title={shownKey ?? undefined}>
              {shownKey}
            </code>
            <button className="ds-mini" id="ds-copy" type="button" title={t('dossier.copyTip')} onClick={() => void copy()}>
              {copyNote ?? t('dossier.copy')}
            </button>
          </div>
        </div>
        <button
          className="ds-close"
          id="ds-close"
          type="button"
          aria-label={t('dossier.close')}
          title={t('dossier.close')}
          ref={closeButton}
          onClick={onClose}
        >
          ✕
        </button>
      </header>
      <div className="ds-stats" id="ds-stats">
        {detail ? (
          <>
            <Stat cls="" n={columns.length} label={t('dossier.statColumns')} i={0} />
            <Stat cls="key" n={columns.filter((c) => keys.has(c.column)).length} label={t('dossier.statKeys')} i={1} />
            <Stat cls="pii" n={columns.filter((c) => c.pii).length} label={t('dossier.statPii')} i={2} />
          </>
        ) : null}
      </div>
      <div className="ds-tools">
        <label className="ds-search">
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="M15.5 15.5 21 21" />
          </svg>
          <input
            id="ds-q"
            type="search"
            ref={searchField}
            placeholder={t('dossier.searchPlaceholder')}
            aria-label={t('dossier.searchLabel')}
            autoComplete="off"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <span className="ds-count" id="ds-count">
            {detail ? (shown.length === columns.length ? `${shown.length}` : `${shown.length} / ${columns.length}`) : ''}
          </span>
        </label>
        <div className="ds-filters" id="ds-filters">
          {detail
            ? FILTERS.map((id) => {
                const n = columns.filter((c) => kind(c)[id]).length;
                return (
                  <button
                    key={id}
                    className="ds-filter"
                    type="button"
                    aria-pressed={filter === id}
                    disabled={!n && id !== 'all'}
                    onClick={() => setFilter(id)}
                  >
                    {`${filterName[id]} · ${n}`}
                  </button>
                );
              })
            : null}
        </div>
      </div>
      <div className="ds-list" id="ds-list" tabIndex={-1} ref={list}>
        {error !== null ? (
          <div className="ds-empty">{t('dossier.failed', {message: error})}</div>
        ) : detail === null ? (
          shownTable ? Array.from({length: SKELETON_ROWS}, (_, i) => <div key={i} className="ds-skel" />) : null
        ) : shown.length ? (
          shown.map((c, i) => <ColumnRow key={`${shownSeq}:${filter}:${term}:${c.key}`} column={c} index={i} term={term} isKey={keys.has(c.column)} />)
        ) : (
          <div className="ds-empty">{t('dossier.empty')}</div>
        )}
      </div>
      <div className={'ds-foot' + (footHidden ? ' hidden' : '')} id="ds-foot">
        {siblings.length && star ? (
          <>
            <div className="lbl">{t('dossier.cluster', {count: star.g.members.length - 1})}</div>
            <div className="ds-sibs">
              {siblings.map((m) => (
                <button
                  key={m.key}
                  className="ds-sib"
                  type="button"
                  title={t('explorer.star.columns', {schema: m.schema, columns: m.columns})}
                  onClick={() => onOpen(m.key)}
                >
                  {m.name}
                  <small>{m.columns}</small>
                </button>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
