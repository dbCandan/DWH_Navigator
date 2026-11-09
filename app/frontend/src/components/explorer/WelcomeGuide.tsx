import {useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties} from 'react';
import {AnswerView} from '@/components/explorer/AnswerView';
import {SearchBox} from '@/components/explorer/SearchBox';
import {useIntl} from '@/contexts/IntlContext';
import {useRootClass} from '@/hooks/useSurface';
import {trapTab} from '@/lib/focusTrap';
import {TOUR_ANSWER, TOUR_PROGRESS, TOUR_QUESTION, tourPace, tourVoteRecorded} from '@/lib/tourSample';
import {markWelcomeSeen} from '@/lib/welcomeGuide';

/**
 * What each step points at and how it moves on: `next` waits for "İleri", `action` for the
 * visitor to do the thing on the sample screen, `auto` moves on by itself.
 */
interface Step {
  key: string;
  target: string | null;
  advance: 'next' | 'action' | 'auto';
}

const STEPS: readonly Step[] = [
  {key: 'intro', target: null, advance: 'next'},
  {key: 'ask', target: '.wt-ask .searchbox', advance: 'action'},
  {key: 'run', target: '.wt-progress', advance: 'auto'},
  {key: 'verdict', target: '.ans-verdict', advance: 'next'},
  {key: 'brief', target: '.brief', advance: 'next'},
  {key: 'best', target: '.ans-main .pick-list', advance: 'action'},
  {key: 'detail', target: '.ans-main .pick.open .pick-body', advance: 'action'},
  // .ans-side dissolves into the main column on narrow screens; .side-guide always has a box.
  {key: 'side', target: '.side-guide', advance: 'next'},
  {key: 'vote', target: '.ans-main .pick.open .fb', advance: 'action'},
  {key: 'report', target: '.answer-top .dl', advance: 'next'},
  {key: 'done', target: null, advance: 'next'},
];

/** The numbered steps: all but the opening and the closing card. */
const COUNTED = STEPS.length - 2;
const BUBBLE_WIDTH = 360;
const GAP = 14;
const EDGE = 16;
/** Taller targets than this share of the window get the bubble in the corner, not beside them. */
const TALL = 0.45;
/** Below this width the bubble is a sheet at the bottom of the window. */
const NARROW = 700;

interface Geometry {
  rect: {top: number; left: number; width: number; height: number} | null;
  bubble: number;
}

const sameGeometry = (a: Geometry, b: Geometry) =>
  a.bubble === b.bubble &&
  (a.rect === b.rect ||
    (a.rect !== null &&
      b.rect !== null &&
      a.rect.top === b.rect.top &&
      a.rect.left === b.rect.left &&
      a.rect.width === b.rect.width &&
      a.rect.height === b.rect.height));

/** Where the bubble goes: beside the target when it fits, else in the corner (or a bottom sheet). */
function bubblePlace(geometry: Geometry): {style: CSSProperties; docked: boolean} {
  const {rect, bubble} = geometry;
  const width = window.innerWidth;
  const height = window.innerHeight;
  if (rect === null) return {style: {}, docked: false};
  if (width < NARROW || rect.height > height * TALL) return {style: {}, docked: true};
  const left = Math.min(Math.max(rect.left, EDGE), width - BUBBLE_WIDTH - EDGE);
  const below = rect.top + rect.height + GAP;
  if (below + bubble <= height - EDGE) return {style: {top: below, left}, docked: false};
  const above = rect.top - GAP - bubble;
  if (above >= EDGE) return {style: {top: above, left}, docked: false};
  return {style: {}, docked: true};
}

/**
 * The main screen's welcome tour, shown once to a browser that never saw it. On a sample copy of
 * the screen, built from the real question bar and answer view with a hand-written answer, the
 * visitor asks, watches the analysis, reads the verdict and the suggestions, opens a table and
 * votes; each step lights up its part and says what to do. Nothing leaves the browser: the vote
 * goes to a stand-in and the report link does nothing. Opening the tour marks it seen.
 */
export function WelcomeGuide({onClose}: {onClose: () => void}) {
  const {t} = useIntl();
  const [index, setIndex] = useState(0);
  const [typed, setTyped] = useState(0);
  const [stage, setStage] = useState(0);
  const [voted, setVoted] = useState(false);
  const [columnRead, setColumnRead] = useState(false);
  const [geometry, setGeometry] = useState<Geometry>({rect: null, bubble: 0});
  const shell = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  const latest = useRef(onClose);
  useEffect(() => {
    latest.current = onClose;
  });
  useRootClass('welcome-open', true);

  useEffect(() => {
    markWelcomeSeen();
  }, []);

  const step = STEPS[index];
  const at = (key: string) => STEPS.findIndex((s) => s.key === key);
  const reached = (key: string) => index >= at(key);
  const next = useCallback(() => setIndex((i) => Math.min(i + 1, STEPS.length - 1)), []);

  // The sample question types itself into the bar.
  const typing = step.key === 'ask' && typed < TOUR_QUESTION.length;
  useEffect(() => {
    if (!typing) return;
    const timer = window.setTimeout(() => setTyped((n) => n + 1), tourPace.typeMs);
    return () => window.clearTimeout(timer);
  }, [typing, typed]);

  // The sample analysis reports its steps, then the answer arrives.
  useEffect(() => {
    if (step.key !== 'run') return;
    const timer = window.setTimeout(
      () => (stage < TOUR_PROGRESS.length ? setStage(stage + 1) : next()),
      tourPace.stageMs,
    );
    return () => window.clearTimeout(timer);
  }, [step.key, stage, next]);

  const ask = () => {
    if (step.key !== 'ask') return;
    setTyped(TOUR_QUESTION.length);
    next();
  };

  // Follow the lit part every frame (the page scrolls, cards open and fold); move on once the
  // visitor did what the step asks.
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const root = scroller.current;
      if (step.key === 'best' && root?.querySelector('.ans-main .pick.open')) {
        next();
        return;
      }
      if (step.key === 'detail' && root?.querySelector('.ans-main .pick.open .detail.on')) setColumnRead(true);
      const el = step.target ? root?.querySelector<HTMLElement>(step.target) : null;
      const box = el?.getBoundingClientRect();
      const measured: Geometry = {
        rect: box ? {top: box.top, left: box.left, width: box.width, height: box.height} : null,
        bubble: bubble.current?.offsetHeight ?? 0,
      };
      setGeometry((was) => (sameGeometry(was, measured) ? was : measured));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [step, next]);

  // Each step brings its part into view and puts the focus where the visitor acts next.
  useLayoutEffect(() => {
    const root = scroller.current;
    // The answer folds its guide cards to fit the window; the step about them opens them.
    if (step.key === 'side')
      for (const card of root?.querySelectorAll<HTMLDetailsElement>('details.side-card') ?? []) card.open = true;
    const el = step.target ? root?.querySelector<HTMLElement>(step.target) : null;
    if (el && typeof el.scrollIntoView === 'function') {
      const tall = el.getBoundingClientRect().height > window.innerHeight * TALL;
      el.scrollIntoView({block: tall ? 'start' : 'center', behavior: 'smooth'});
    }
    if (step.advance === 'next') primary.current?.focus({preventScroll: true});
    else if (step.key === 'ask') root?.querySelector<HTMLButtonElement>('.wt-ask .primary')?.focus({preventScroll: true});
    else bubble.current?.focus({preventScroll: true});
  }, [step]);

  // Esc leaves the tour before the page's own keys see it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      latest.current();
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, []);

  const sendVote = useCallback(() => {
    setVoted(true);
    return tourVoteRecorded();
  }, []);

  // Once done, "İleri" appears: a 👎's reason or another column can still be picked before it.
  const acted = (step.key === 'vote' && voted) || (step.key === 'detail' && columnRead);
  useEffect(() => {
    if (acted) primary.current?.focus({preventScroll: true});
  }, [acted]);

  const centred = step.target === null;
  const place = bubblePlace(geometry);
  const rect = geometry.rect;
  const number = index >= 1 && index <= COUNTED ? index : null;
  const waiting = step.advance === 'action' && !acted;
  const hint =
    step.key === 'ask'
      ? t(typing ? 'welcome.ask.typing' : 'welcome.ask.action')
      : step.advance === 'action'
        ? t(acted ? `welcome.${step.key}.thanks` : `welcome.${step.key}.action`)
        : '';

  return (
    <div
      className="wt"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wt-title"
      ref={shell}
      onKeyDown={(event) => trapTab(event, shell.current)}
    >
      <div className="wt-stage" ref={scroller} aria-hidden={centred ? true : undefined}>
        <div className="wt-top">
          <span className="wt-badge">{t('welcome.badge')}</span>
        </div>
        <div className="wt-ask">
          <p className="wt-title">{t('explorer.hero.title')}</p>
          <SearchBox
            sample
            value={TOUR_QUESTION.slice(0, typed)}
            onChange={() => undefined}
            onSubmit={ask}
            onStop={() => undefined}
            busy={step.key === 'run'}
            onAttach={() => undefined}
          />
        </div>
        {step.key === 'run' ? (
          <ol className="wt-progress" aria-live="polite">
            {TOUR_PROGRESS.map((key, n) => (
              <li key={key} className={n < stage ? 'done' : n === stage ? 'now' : ''}>
                {t(`welcome.run.${key}`)}
              </li>
            ))}
          </ol>
        ) : null}
        {reached('verdict') ? (
          <div className="wt-out">
            <AnswerView
              answer={TOUR_ANSWER}
              onRedo={() => undefined}
              onReport={() => undefined}
              reportHref="#"
              sendVote={sendVote}
            />
          </div>
        ) : null}
      </div>

      {centred ? (
        <div className="wt-scrim" />
      ) : rect ? (
        <div
          className="wt-spot"
          aria-hidden="true"
          style={{top: rect.top - 8, left: rect.left - 8, width: rect.width + 16, height: rect.height + 16}}
        />
      ) : null}

      <div
        className={'wt-bubble' + (centred ? ' centred' : place.docked ? ' docked' : '')}
        style={centred ? undefined : place.style}
        ref={bubble}
        tabIndex={-1}
      >
        <div className="wt-head">
          <span className="wt-kicker">
            {number !== null ? t('welcome.step', {current: number, total: COUNTED}) : t('welcome.label')}
          </span>
          <button className="wt-close" type="button" aria-label={t('welcome.close')} title={t('welcome.close')} onClick={onClose}>
            ✕
          </button>
        </div>
        <h2 id="wt-title">{t(`welcome.${step.key}.title`)}</h2>
        <p className="wt-body">{t(`welcome.${step.key}.body`)}</p>
        {step.key === 'done' ? (
          <ul className="wt-tips">
            {[1, 2, 3].map((n) => (
              <li key={n}>{t(`welcome.done.${n}`)}</li>
            ))}
          </ul>
        ) : null}
        {hint ? (
          <p className={'wt-hint' + (waiting ? ' wait' : ' ok')} role="status">
            {hint}
          </p>
        ) : null}
        <div className="wt-actions">
          {step.key === 'intro' ? (
            <button type="button" className="wt-later" onClick={onClose}>
              {t('welcome.later')}
            </button>
          ) : null}
          {step.advance === 'next' || acted ? (
            <button
              type="button"
              className="wt-next"
              ref={primary}
              onClick={step.key === 'done' ? onClose : next}
            >
              {step.key === 'intro' ? t('welcome.start') : step.key === 'done' ? t('welcome.finish') : t('welcome.next')}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
