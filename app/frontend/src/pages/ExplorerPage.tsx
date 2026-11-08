import {lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent} from 'react';
import {CompassMark} from '@/components/brand/CompassMark';
import {AnswerView} from '@/components/explorer/AnswerView';
import {Dossier, type OpenTable} from '@/components/explorer/Dossier';
import {SearchBox} from '@/components/explorer/SearchBox';
import {ListFormatHelp, TermListView} from '@/components/explorer/TermListView';
import {useIntl} from '@/contexts/IntlContext';
import {useAsk} from '@/hooks/useAsk';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useGalaxy} from '@/hooks/useGalaxy';
import {useServiceStatus} from '@/hooks/useServiceStatus';
import {useRootClass, useSurface} from '@/hooks/useSurface';
import {useTermList} from '@/hooks/useTermList';
import {ApiError} from '@/lib/apiClient';
import {config} from '@/lib/config';
import type {CosmosEngine} from '@/lib/cosmos/engine';
import {XLSX_MEDIA_TYPE} from '@/lib/excelUpload';
import {explorerErrorText} from '@/lib/explorerErrors';
import {statusView} from '@/lib/serviceStatus';
import {forgetTabAnalysis, recallTabAnalysis} from '@/lib/tabAnalysis';
import {AnalysisService} from '@/services/analyses';
import '@/components/explorer/explorer.css';

// The map is a separate, lazily loaded part: the shell and the question bar never wait for it
// (dictionary-explorer Requirement 5).
const CosmosMap = lazy(() => import('@/components/explorer/CosmosMap'));

/** How long the compass settles after an analysis (index.html: the "found" class). */
const SETTLE_MS = 1200;

/** Scroll states of the source page: the veil behind the top line and the HUD's retreat. */
function useScrollClasses(): void {
  const [scroll, setScroll] = useState(() => window.scrollY);
  useEffect(() => {
    const onScroll = () => setScroll(window.scrollY);
    window.addEventListener('scroll', onScroll, {passive: true});
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  useRootClass('lifted', scroll > 6);
  useRootClass('scrolled', scroll > 120);
}

/** What the space under the bar shows: the question's outcome or the term list (index.html #ask-out). */
type Pane =
  | {kind: 'ask'}
  | {kind: 'list'}
  /** "“{name}” okunuyor…" while the file is uploaded. */
  | {kind: 'reading'; name: string}
  /** The refused file with the accepted layout. */
  | {kind: 'refused'; name: string; message: string};

/** Only files are dropped on the page (index.html Bulk). */
const carriesFiles = (event: DragEvent) => [...(event.dataTransfer?.types ?? [])].includes('Files');

/**
 * Drop an Excel list anywhere on the page: the bar lights up while a file is dragged over the
 * window (list-search Requirement 17).
 */
function useListDrop(onFile: (file: File) => void): void {
  const [dropping, setDropping] = useState(false);
  const latest = useRef(onFile);
  useEffect(() => {
    latest.current = onFile;
  });
  useRootClass('dropping', dropping);
  useEffect(() => {
    let depth = 0;
    const enter = (event: DragEvent) => {
      if (!carriesFiles(event)) return;
      depth++;
      setDropping(true);
    };
    const leave = (event: DragEvent) => {
      if (!carriesFiles(event) || --depth > 0) return;
      depth = 0;
      setDropping(false);
    };
    const over = (event: DragEvent) => {
      if (carriesFiles(event)) event.preventDefault();
    };
    const drop = (event: DragEvent) => {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDropping(false);
      const file = event.dataTransfer?.files[0];
      if (file) latest.current(file);
    };
    window.addEventListener('dragenter', enter);
    window.addEventListener('dragleave', leave);
    window.addEventListener('dragover', over);
    window.addEventListener('drop', drop);
    return () => {
      window.removeEventListener('dragenter', enter);
      window.removeEventListener('dragleave', leave);
      window.removeEventListener('dragover', over);
      window.removeEventListener('drop', drop);
    };
  }, []);
}

/**
 * The main screen (`/`): the "Evren" sky, the top line with the brand, the question bar (in the
 * middle at first, then docked in the top line as the page's heading), the status pill and the
 * session area, the warning under the bar and the answer (dictionary-explorer Requirement 1, 2, 5,
 * 17; question-analysis Requirement 19–22), the table file (Requirement 9, 11-14), the term list
 * and its pill (list-search Requirement 17).
 */
export default function ExplorerPage() {
  const {t} = useIntl();
  useSurface('explorer');
  useDocumentTitle(t('explorer.documentTitle'));
  useScrollClasses();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState<string | undefined>(undefined);
  const [docked, setDocked] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const header = useRef<HTMLElement>(null);
  const hero = useRef<HTMLDivElement>(null);
  const foot = useRef<HTMLElement>(null);
  const engine = useRef<CosmosEngine | null>(null);
  const flipFrom = useRef<DOMRect | null>(null);
  const {status, failed: statusFailed, reload: reloadStatus} = useServiceStatus();
  const statusRef = useRef(status);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const galaxy = useGalaxy(status);

  const {running, outcome, ask, stop, clear} = useAsk({
    engine: () => engine.current,
    status: () => statusRef.current,
    onUnavailable: reloadStatus,
  });
  const lists = useTermList();
  const [pane, setPane] = useState<Pane>({kind: 'ask'});
  const [opened, setOpened] = useState<ReadonlySet<number>>(() => new Set());
  // Showing the list removes the pill; it comes back when the list answers a poll or a question
  // is answered (index.html Bulk.pill). On opening the page it shows the newest list (list-search
  // Requirement 15).
  const [pillGone, setPillGone] = useState<{polls: number; outcome: typeof outcome} | null>(null);
  const pillArmed =
    pillGone === null || lists.polls !== pillGone.polls || (outcome !== pillGone.outcome && outcome?.kind === 'answer');
  useRootClass('docked', docked);
  useRootClass('busy', running);
  const hasResults = pane.kind === 'list' || (pane.kind === 'ask' && outcome?.kind === 'answer');
  useRootClass('has-results', hasResults);
  // The answer's panels sit over the map: its star labels would show through them.
  useEffect(() => engine.current?.quiet(hasResults), [hasResults]);

  // The table file: one shared opening for every place that offers a table (Requirement 14).
  const [table, setTable] = useState<OpenTable | null>(null);
  const openings = useRef(0);
  const openTable = useCallback((key: string) => {
    const star = engine.current?.select(key) ?? null;
    openings.current += 1;
    setTable({key, star, seq: openings.current});
  }, []);
  const closeTable = useCallback(() => {
    engine.current?.select(null);
    setTable(null);
  }, []);
  const hasTable = useCallback((key: string) => engine.current?.node(key) != null, []);

  // The compass searches while the analysis runs ("busy") and settles once it ends ("found").
  const wasRunning = useRef(false);
  useEffect(() => {
    const root = document.documentElement;
    if (running) {
      wasRunning.current = true;
      root.classList.remove('found');
      return;
    }
    if (!wasRunning.current) return;
    wasRunning.current = false;
    root.classList.add('found');
    const timer = window.setTimeout(() => root.classList.remove('found'), SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      root.classList.remove('found');
    };
  }, [running]);

  const view = status ? statusView(status, t) : null;
  const warn = view?.warn ?? '';

  // Header and footer differ in height; balance them so the landing block sits at the window's
  // centre (index.html centreHero), again when the warning line changes.
  useLayoutEffect(() => {
    const centre = () => {
      if (!header.current || !hero.current || !foot.current) return;
      const d = header.current.getBoundingClientRect().bottom - foot.current.offsetHeight;
      hero.current.style.setProperty('--shift-top', Math.max(0, -d) + 'px');
      hero.current.style.setProperty('--shift-bottom', Math.max(0, d) + 'px');
    };
    centre();
    window.addEventListener('resize', centre);
    return () => window.removeEventListener('resize', centre);
  }, [warn]);

  /** After the first question the bar glides up into the top line and stays there. */
  const foldSearch = useCallback(() => {
    if (document.documentElement.classList.contains('docked')) return;
    flipFrom.current = document.querySelector('#hero .searchbox')?.getBoundingClientRect() ?? null;
    setDocked(true);
  }, []);

  useLayoutEffect(() => {
    const first = flipFrom.current;
    flipFrom.current = null;
    if (!docked || first === null) return;
    const box = document.querySelector<HTMLElement>('#bar-slot .searchbox');
    if (!box || typeof box.animate !== 'function') return;
    const last = box.getBoundingClientRect();
    if (!last.width || !last.height) return;
    box.animate(
      [
        {
          transformOrigin: '0 0',
          transform: `translate(${first.left - last.left}px, ${first.top - last.top}px) scale(${first.width / last.width}, ${first.height / last.height})`,
        },
        {transformOrigin: '0 0', transform: 'none'},
      ],
      {duration: 560, easing: 'cubic-bezier(.6,0,.2,1)'},
    );
  }, [docked]);

  const start = useCallback(
    (text: string, fresh: boolean) => {
      closeTable();
      setPane({kind: 'ask'});
      foldSearch();
      field.current?.blur();
      window.scrollTo({top: 0});
      setAsked(text);
      void ask(text, fresh);
    },
    [ask, foldSearch, closeTable],
  );

  function submit() {
    if (running) return;
    const text = question.trim();
    if (!text) {
      field.current?.focus();
      return;
    }
    // A table's own name opens its file as if its star was clicked (Requirement 9); the focus
    // comes back to the bar when the file closes.
    const exact = engine.current?.find(text) ?? null;
    if (exact) {
      openTable(exact.key);
      return;
    }
    start(text, false);
  }

  /** The list heads the page like an answer does. */
  const showList = useCallback(() => {
    foldSearch();
    setPane({kind: 'list'});
    setPillGone({polls: lists.polls, outcome});
  }, [foldSearch, lists.polls, outcome]);

  const startList = useCallback(
    async (file: File) => {
      if (lists.list?.status === 'running' && lists.following) {
        showList();
        return;
      }
      closeTable();
      foldSearch();
      field.current?.blur();
      window.scrollTo({top: 0});
      setQuestion('');
      setAsked(undefined);
      setOpened(new Set());
      setPane({kind: 'reading', name: file.name});
      const started = await lists.start(file);
      if (started.kind === 'refused') setPane({kind: 'refused', name: file.name, message: explorerErrorText(started.error, t)});
      else showList();
    },
    [lists, closeTable, foldSearch, showList, t],
  );
  useListDrop((file) => void startList(file));
  const picker = useRef<HTMLInputElement>(null);
  const toggleTerm = useCallback(
    (position: number) =>
      setOpened((was) => {
        const next = new Set(was);
        if (next.has(position)) next.delete(position);
        else next.add(position);
        return next;
      }),
    [],
  );
  const redo = useCallback(
    (query: string) => {
      setQuestion(query);
      start(query, true);
    },
    [start],
  );

  // A reload follows the question this tab started, never another tab's (Requirement 19, Decision 26).
  useEffect(() => {
    const id = recallTabAnalysis();
    if (id === null) return;
    let live = true;
    AnalysisService.get(id).then(
      (job) => {
        if (!live) return;
        if (job.state !== 'queued' && job.state !== 'running') {
          forgetTabAnalysis(id);
          return;
        }
        setQuestion(job.query);
        setAsked(job.query);
        setDocked(true);
        void ask(job.query, false, job);
      },
      (error) => {
        if (error instanceof ApiError && error.status === 404) forgetTabAnalysis(id);
      },
    );
    return () => {
      live = false;
    };
  }, [ask]);

  // In the heading: "/" focuses the bar, Esc stops the analysis or leaves the bar.
  useEffect(() => {
    if (!docked) return;
    const onKey = (event: KeyboardEvent) => {
      const active = document.activeElement;
      if (event.key === 'Escape' && running) {
        event.preventDefault();
        stop();
      } else if (event.key === 'Escape' && active === field.current) field.current?.blur();
      else if (event.key === '/' && !/^(INPUT|TEXTAREA)$/.test(active?.tagName ?? '')) {
        event.preventDefault();
        field.current?.focus();
        field.current?.select();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [docked, running, stop]);

  /** "Yeni başlangıç": back to the landing view without reloading the page. */
  function restart(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    window.scrollTo({top: 0});
    // A running analysis goes on, as after a reload of the source page that reconnects to it.
    if (running) return;
    clear();
    closeTable();
    setPane({kind: 'ask'});
    setPillGone(null);
    setQuestion('');
    setAsked(undefined);
    setDocked(false);
    engine.current?.focus([]);
    requestAnimationFrame(() => field.current?.focus());
  }

  const onEngine = useCallback((created: CosmosEngine | null) => {
    engine.current = created;
  }, []);

  const searchBox = (
    <SearchBox
      value={question}
      onChange={setQuestion}
      onSubmit={submit}
      onStop={stop}
      busy={running}
      docked={docked}
      title={docked ? asked : undefined}
      textareaRef={field}
      onAttach={() => picker.current?.click()}
    />
  );

  return (
    <>
      <Suspense fallback={null}>
        <CosmosMap galaxy={galaxy} onEngine={onEngine} onStarClick={openTable} onSkyClick={closeTable} />
      </Suspense>
      <Dossier table={table} onOpen={openTable} onClose={closeTable} />
      <header className="top" ref={header}>
        <div className="wrap">
          <a className="brand" href="/" title={t('explorer.brand.restart')} onClick={restart}>
            <CompassMark />
            <div>
              <b>{t('explorer.brand.name')}</b>
              <span>{t('explorer.brand.tagline')}</span>
            </div>
          </a>
          <div className="slot" id="bar-slot">
            {docked ? searchBox : null}
          </div>
          <div className="tools">
            {lists.list && lists.following && pane.kind !== 'list' && pillArmed ? (
              <button
                className="pill listpill"
                id="listpill"
                type="button"
                title={t('list.pillTip')}
                onClick={showList}
              >
                <i className={'dot' + (lists.list.status === 'running' ? ' on' : '')} />
                {lists.list.status === 'running'
                  ? t('list.pillRunning', {done: lists.list.done, total: lists.list.total})
                  : t('list.pillResult')}
              </button>
            ) : null}
            <div className="status" id="status">
              {view ? (
                <span className={'pill ' + view.tone} title={view.tip}>
                  <i className={'dot' + (view.tone ? '' : ' on')} />
                  {view.label}
                </span>
              ) : statusFailed ? (
                <span className="pill">{t('explorer.status.unreachable')}</span>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <main className="wrap">
        <section id="tab-ask">
          <div className={'hero' + (docked ? ' compact' : '')} id="hero" ref={hero}>
            <h1>{t('explorer.hero.title')}</h1>
            {docked ? null : searchBox}
            <div className={'model-warn' + (view?.tone === 'bad' ? ' bad' : '')} id="model-warn" role="status">
              {warn}
            </div>
            <input
              type="file"
              id="xl-file"
              ref={picker}
              accept={'.xlsx,' + XLSX_MEDIA_TYPE}
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (file) void startList(file);
              }}
            />
          </div>
          <div id="ask-out">
            {pane.kind === 'list' && lists.list ? (
              <TermListView
                list={lists.list}
                opened={opened}
                onToggle={toggleTerm}
                onStop={lists.stop}
                onResume={lists.resume}
                onRedo={redo}
                openTable={openTable}
                hasTable={hasTable}
                catalog={galaxy ?? undefined}
              />
            ) : pane.kind === 'reading' ? (
              <div className="stopped" role="status">
                {t('list.reading', {name: pane.name})}
              </div>
            ) : pane.kind === 'refused' ? (
              <ListFormatHelp name={pane.name} message={pane.message} />
            ) : pane.kind === 'list' ? null : outcome?.kind === 'answer' ? (
              <AnswerView
                answer={outcome.answer}
                reportHref={`${config.apiPrefix}/analyses/${encodeURIComponent(outcome.analysisId)}/report`}
                onReport={() => void AnalysisService.report(outcome.analysisId).catch(() => undefined)}
                onRedo={() => redo(outcome.answer.query)}
                openTable={openTable}
                hasTable={hasTable}
                catalog={galaxy ?? undefined}
              />
            ) : outcome?.kind === 'stopped' ? (
              <div className="stopped" role="status">
                {t('explorer.ask.stopped')}
              </div>
            ) : outcome?.kind === 'interrupted' ? (
              <div className="stopped" role="status">
                {t('explorer.ask.interrupted')}
              </div>
            ) : outcome?.kind === 'failed' ? (
              <div className="error">{t('explorer.ask.failed', {message: outcome.message})}</div>
            ) : null}
          </div>
        </section>
      </main>
      <footer id="foot" ref={foot} />
    </>
  );
}
