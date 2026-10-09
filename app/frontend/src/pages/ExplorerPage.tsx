import {lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent} from 'react';
import {CompassMark} from '@/components/brand/CompassMark';
import {AnswerView} from '@/components/explorer/AnswerView';
import {SearchBox} from '@/components/explorer/SearchBox';
import {SessionArea} from '@/components/explorer/SessionArea';
import {useIntl} from '@/contexts/IntlContext';
import {useAsk} from '@/hooks/useAsk';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useServiceStatus} from '@/hooks/useServiceStatus';
import {useRootClass, useSurface} from '@/hooks/useSurface';
import {config} from '@/lib/config';
import type {CosmosEngine} from '@/lib/cosmos/engine';
import {SAMPLE_GALAXY} from '@/lib/cosmos/sampleGalaxy';
import {statusView} from '@/lib/serviceStatus';
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

const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * The main screen (`/`): the "Evren" sky, the top line with the brand, the question bar (in the
 * middle at first, then docked in the top line as the page's heading), the status pill and the
 * session area, the warning under the bar and the answer (dictionary-explorer Requirement 1, 2, 5,
 * 17; question-analysis Requirement 19–22). The table file, the term list and the votes come with
 * the capabilities that own them.
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

  const {running, outcome, ask, stop, clear} = useAsk({
    engine: () => engine.current,
    status: () => statusRef.current,
    onUnavailable: reloadStatus,
  });
  useRootClass('docked', docked);
  useRootClass('busy', running);
  useRootClass('has-results', outcome?.kind === 'answer');

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
    if (!docked || first === null || reduceMotion()) return;
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
      foldSearch();
      field.current?.blur();
      window.scrollTo({top: 0});
      setAsked(text);
      void ask(text, fresh);
    },
    [ask, foldSearch],
  );

  function submit() {
    if (running) return;
    const text = question.trim();
    if (!text) {
      field.current?.focus();
      return;
    }
    start(text, false);
  }

  // Reopening the page follows the person's running question (Requirement 19).
  useEffect(() => {
    let live = true;
    AnalysisService.active().then(
      (job) => {
        if (!live || job === null) return;
        setQuestion(job.query);
        setAsked(job.query);
        setDocked(true);
        void ask(job.query, false, job);
      },
      () => undefined,
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
    />
  );

  return (
    <>
      <Suspense fallback={null}>
        <CosmosMap galaxy={SAMPLE_GALAXY} onEngine={onEngine} />
      </Suspense>
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
            <SessionArea />
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
          </div>
          <div id="ask-out">
            {outcome?.kind === 'answer' ? (
              <AnswerView
                answer={outcome.answer}
                reportHref={`${config.apiPrefix}/analyses/${encodeURIComponent(outcome.analysisId)}/report`}
                onReport={() => void AnalysisService.report(outcome.analysisId).catch(() => undefined)}
                onRedo={() => {
                  setQuestion(outcome.answer.query);
                  start(outcome.answer.query, true);
                }}
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
