import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent,
  type ReactNode,
} from 'react';
import {Breakable} from '@/components/explorer/Breakable';
import {AnswerVote, ApprovedMark, PickMark, VoteBadge, VoteBar, type SendVote} from '@/components/explorer/Votes';
import {useIntl} from '@/contexts/IntlContext';
import {
  answerConcepts,
  movedBefore,
  cardId,
  conceptParts,
  NOTE_TONE,
  pct,
  richTokenizer,
  splitSummary,
  verdictClass,
  type RichToken,
} from '@/lib/answerText';
import {VoteService} from '@/services/votes';
import type {AnalysisAnswer, AnswerColumn, AnswerObject} from '@/types/analysis';
import type {VoteIn} from '@/types/feedback';

/*
 * The answer view (question-analysis Requirement 21; index.html answerView, foundBlock,
 * overview, resultCard, sideCard, richOf): the source's elements, class names and texts. The
 * analyst's text is rendered as plain text only. The vote elements (answer-feedback
 * Requirement 11-13) are in Votes.tsx; the tables people approved or rejected are shown apart.
 */

type Translate = (key: string, values?: Record<string, string | number>) => string;

interface Shared {
  t: Translate;
  rich: (text: string) => RichToken[];
  /** Open a suggestion's row and bring it into view (source jumpTo). */
  jumpTo: (m: AnswerObject) => void;
  /** The table file of dictionary-explorer, when the page offers it. */
  openTable?: (key: string) => void;
  /** Whether the table file can open this key (it has a star on the map). */
  hasTable?: (key: string) => boolean;
  /** A vote on this answer or on one of its tables. */
  vote: (body: Pick<VoteIn, 'scope' | 'table_key'>) => SendVote;
  /** The person's own last votes in this question (table key, "" for the answer). */
  mine: Record<string, 'up' | 'down'>;
}

const AnswerContext = createContext<Shared | null>(null);

function useShared(): Shared {
  const shared = useContext(AnswerContext);
  if (shared === null) throw new Error('answer parts render inside AnswerView');
  return shared;
}

const VERDICT_WORD: Record<string, [string, string]> = {
  VAR: ['✓', 'answer.verdict.found'],
  'KISMEN VAR': ['◐', 'answer.verdict.partial'],
  BULUNAMADI: ['✕', 'answer.verdict.notFound'],
};

/** Prose with its table and column names made light to read. */
function Rich({text}: {text: string}) {
  const {t, rich, jumpTo, openTable, hasTable} = useShared();
  return (
    <>
      {rich(text).map((token, i) => {
        if (token.kind === 'text') return <Fragment key={i}>{token.text}</Fragment>;
        if (token.kind === 'column')
          return (
            <code key={i} className="cn">
              {token.text}
            </code>
          );
        const toCard = token.suggested && token.object !== null;
        const toFile = !toCard && openTable !== undefined && (hasTable?.(token.key) ?? false);
        if (toCard || toFile)
          return (
            <button
              key={i}
              className="tn"
              type="button"
              title={t(toCard ? 'answer.openDetail' : 'answer.openDictionary', {key: token.key})}
              onClick={(event) => {
                if (toCard && token.object) return jumpTo(token.object);
                // The map's sky click would close the file this click opens (as "Kolonlar" does).
                event.stopPropagation();
                openTable?.(token.key);
              }}
            >
              <Breakable name={token.name} />
            </button>
          );
        return (
          <span key={i} className="tn" title={token.key}>
            <Breakable name={token.name} />
          </span>
        );
      })}
    </>
  );
}

const RING_R = 22;
const RING_C = 2 * Math.PI * RING_R;

/** Confidence as a ring: the arc is the score, its colour the level; number and level are written. */
function Ring({m}: {m: AnswerObject}) {
  const {t} = useShared();
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    // The arc grows once the card is on the page (source growRings: two frames later).
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setGrown(true));
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, []);
  const p = Math.max(0, Math.min(1, m.score || 0));
  const score = pct(m.score);
  const before = movedBefore(m);
  return (
    <div
      className={'ring lc-' + m.level}
      role="img"
      aria-label={t('answer.ring', {score, level: m.level})}
      title={t('answer.ringTip', {score}) + (before !== null ? t('vote.ringBefore', {before}) : '')}
    >
      <svg viewBox="0 0 52 52" width="52" height="52" aria-hidden="true">
        <circle cx="26" cy="26" r={RING_R} className="ring-track" />
        <circle
          cx="26"
          cy="26"
          r={RING_R}
          className="ring-arc"
          strokeDasharray={`${grown ? (RING_C * p).toFixed(1) : '0'} ${RING_C.toFixed(1)}`}
          transform="rotate(-90 26 26)"
        />
      </svg>
      <b>{score}</b>
      <span>{m.level}</span>
    </div>
  );
}

/** Long prose shows its first lines; a click opens the rest (only when cut). */
function Clamp({as: Tag, className, children}: {as: 'p' | 'div'; className?: string; children: ReactNode}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLParagraphElement & HTMLDivElement>(null);
  function toggle(event: MouseEvent) {
    if ((event.target as Element).closest('a, button')) return; // a table chip leads to its card
    const el = ref.current;
    if (!el || (!open && el.scrollHeight <= el.clientHeight + 1)) return;
    setOpen(!open);
  }
  const cls = [className, 'clamp', open ? 'open' : ''].filter(Boolean).join(' ');
  return (
    <Tag ref={ref} className={cls} onClick={toggle}>
      {children}
    </Tag>
  );
}

const SHOWN_COLUMNS = 6;

/** The suggestion's columns: the first six, "+N kolon", and one column's detail at a time. */
function ColumnChips({m}: {m: AnswerObject}) {
  const {t} = useShared();
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  const rest = m.columns.length - SHOWN_COLUMNS;
  const shown: AnswerColumn | null = openIndex === null ? null : m.columns[openIndex];
  const roleName = (role: string) => (role === 'yapısal' ? t('answer.roleStructural') : role);
  return (
    <>
      <div className="cols">
        {m.columns.map((c, i) => (
          <button
            key={i}
            className={'col' + (!all && i >= SHOWN_COLUMNS ? ' hidden' : '')}
            type="button"
            aria-expanded={openIndex === i}
            title={(c.role ? roleName(c.role) + ' · ' : '') + c.description}
            onClick={() => setOpenIndex(openIndex === i ? null : i)}
          >
            <span>
              <Breakable name={c.column} />
            </span>
          </button>
        ))}
        {rest > 0 && !all ? (
          <button className="col more" type="button" onClick={() => setAll(true)}>
            {t('answer.moreColumns', {count: rest})}
          </button>
        ) : null}
      </div>
      <div className={'detail' + (shown ? ' on' : '')}>
        {shown ? (
          <>
            <div>
              <span className="k">{shown.column}</span>
              <span className="faint">{'  ' + shown.object}</span>
            </div>
            <div style={{marginTop: '4px'}}>{shown.description}</div>
            {shown.synonyms.length ? (
              <div className="syn">{t('answer.synonyms', {items: shown.synonyms.join(', ')})}</div>
            ) : null}
            {shown.signals.map((s, i) => (
              <div key={'s' + i} className="sig">
                {'✓ ' + s}
              </div>
            ))}
            {shown.caveats.map((s, i) => (
              <div key={'c' + i} className="faint" style={{color: 'var(--mid)'}}>
                {'! ' + s}
              </div>
            ))}
          </>
        ) : null}
      </div>
    </>
  );
}

const COMPONENTS = ['best_column', 'coverage', 'time', 'granularity', 'topic'];

/** The score's components and the analyst's confidence as bars. */
function Bars({m}: {m: AnswerObject}) {
  const {t} = useShared();
  const label = (k: string) => (COMPONENTS.includes(k) ? t(`answer.component.${k}`) : k);
  return (
    <div className="bars">
      {Object.entries(m.components).map(([k, v]) => (
        <div key={k} className="bar">
          {t('answer.componentBar', {label: label(k), score: pct(v)})}
          <div className="track">
            <div className="fill" style={{width: `${pct(v)}%`}} />
          </div>
        </div>
      ))}
      {m.llm != null ? (
        <div className="bar llm">
          {t('answer.llmConfidence', {score: pct(m.llm)})}
          <div className="track">
            <div className="fill" style={{width: `${pct(m.llm)}%`}} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Opens the table's every column in the table file of the map. */
function ColumnsButton({m}: {m: AnswerObject}) {
  const {t, openTable} = useShared();
  return (
    <button
      className="res-cols"
      type="button"
      title={t('answer.columnsTip', {key: m.key})}
      onClick={(event) => {
        event.stopPropagation();
        openTable?.(m.key);
      }}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M4 5h16M4 10h16M4 15h16M4 20h10"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      {t('answer.columns')}
    </button>
  );
}

interface PickProps {
  m: AnswerObject;
  open: boolean;
  onToggle: () => void;
  /** A near candidate or a rejected table: no rank, no element id. */
  aside?: boolean;
  /** A table people rejected: shown faded. */
  dim?: boolean;
}

/** A suggestion as one row (rank, name, confidence) that opens its card under it. */
function ResultCard({m, open, onToggle, aside = false, dim = false}: PickProps) {
  const {t, vote, mine} = useShared();
  const id = aside ? undefined : cardId(m.key);
  const bodyId = aside ? undefined : cardId(m.key) + '-body';
  const covered = new Set(m.covered);
  const long = new Set(m.long_format);
  const concepts = [...m.covered, ...m.missing];
  const score = pct(m.score);
  const before = movedBefore(m);
  return (
    <article
      className={`pick lc-${m.level}` + (dim ? ' dim' : '') + (open ? ' open' : '')}
      id={id}
      style={{'--i': m.rank || 0} as CSSProperties}
    >
      <button
        className="pick-row"
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        title={t('answer.pickTip', {key: m.key, score, level: m.level}) + (before !== null ? t('vote.pickBefore', {before}) : '')}
        onClick={onToggle}
      >
        <span className="pk-n">{!aside && m.rank ? m.rank : '·'}</span>
        <span className="pk-name">
          {m.name}
          <PickMark m={m} />
        </span>
        <span className="pk-bar" aria-hidden="true">
          <i style={{'--w': `${score}%`} as CSSProperties} />
        </span>
        <span className="pk-pct">{'%' + score}</span>
        <span className="pk-lv">{m.level}</span>
        <span className="pk-chev" aria-hidden="true">
          ▸
        </span>
      </button>
      <div className="pick-body" id={bodyId}>
        <div className="res-path">
          <code>{`${m.database}.${m.schema}`}</code>
          {m.groups.length ? ' · ' + m.groups.join(', ') : null} <VoteBadge m={m} />
          <ColumnsButton m={m} />
        </div>
        {m.covers ? <div className="res-covers">{m.covers}</div> : null}
        <Clamp as="p" className="res-reason">
          <Rich text={m.reason} />
        </Clamp>
        {m.caveat.length ? (
          <div className="res-warn">
            {m.caveat.map((c, i) => (
              <Clamp key={i} as="div">
                <span className="res-warn-i" aria-hidden="true">
                  {'⚠ '}
                </span>
                <Rich text={c} />
              </Clamp>
            ))}
          </div>
        ) : null}
        <ColumnChips m={m} />
        <div className="res-foot">
          <details>
            <summary>{t('answer.details')}</summary>
            {m.usage ? (
              <div className="usage res-usage">
                <span className="res-use-i" aria-hidden="true">
                  →
                </span>
                <span>
                  <Rich text={m.usage} />
                </span>
              </div>
            ) : null}
            {concepts.length ? (
              <div className="chips">
                {concepts.map((c, i) => (
                  <span
                    key={i}
                    className={'chip ' + (long.has(c) ? 'long' : covered.has(c) ? 'on' : 'off')}
                    title={
                      long.has(c)
                        ? t('answer.concept.long', {dimension: m.dimension})
                        : covered.has(c)
                          ? t('answer.concept.covered')
                          : t('answer.concept.uncovered')
                    }
                  >
                    {c}
                  </span>
                ))}
              </div>
            ) : null}
            <Bars m={m} />
          </details>
          <VoteBar
            label={t('vote.question')}
            mine={mine[m.key] ?? ''}
            send={vote({scope: 'table', table_key: m.key})}
          />
        </div>
      </div>
    </article>
  );
}

/** A list of suggestion rows; one row open at a time. */
function PickList({
  items,
  aside = false,
  dim = false,
  className = 'pick-list',
  openKey,
  onOpen,
}: {
  items: readonly AnswerObject[];
  aside?: boolean;
  dim?: boolean;
  className?: string;
  openKey: string | null;
  onOpen: (key: string | null) => void;
}) {
  return (
    <div className={className}>
      {items.map((m, i) => (
        <ResultCard
          key={m.key + i}
          m={m}
          aside={aside}
          dim={dim}
          open={openKey === m.key}
          onToggle={() => onOpen(openKey === m.key ? null : m.key)}
        />
      ))}
    </div>
  );
}

/** A folding guide card: the matrix starts open, the prose ones closed with their count. */
function SideCard({title, cls, count, children}: {title: string; cls: string; count?: number; children: ReactNode}) {
  return (
    <details className={'side-card ' + cls} open={cls === 'matrix'}>
      <summary className="side-h">
        {title}
        {count ? <span className="side-n">{count}</span> : null}
      </summary>
      {children}
    </details>
  );
}

const CELL_SYMBOL = {on: '●', long: '◐', off: '○'} as const;
const SHOWN_CONCEPTS = 8;

/** "Hangi tablo neyi karşılıyor": which table covers which part of the request. */
function Overview({answer}: {answer: AnalysisAnswer}) {
  const {t, jumpTo} = useShared();
  const objects = answer.objects;
  const concepts = answerConcepts(objects);
  const cols = concepts.slice(0, SHOWN_CONCEPTS);
  if (!objects.length || !cols.length) return null;
  return (
    <SideCard title={t('answer.matrix')} cls="matrix">
      <div className="ov-mx-wrap">
        <table className="ov-mx">
          <thead>
            <tr>
              <th scope="col">
                <span className="sr">{t('answer.matrixTable')}</span>
              </th>
              {cols.map((c, i) => (
                <th key={i} scope="col" title={c}>
                  <span>{c}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objects.map((m) => (
              <tr key={m.key}>
                <th scope="row">
                  <button type="button" onClick={() => jumpTo(m)} title={m.name}>
                    <span className="ov-n">{m.rank}</span>
                    {m.name}
                  </button>
                </th>
                {cols.map((c, i) => {
                  const k = m.long_format.includes(c) ? 'long' : m.covered.includes(c) ? 'on' : 'off';
                  const state = t(`answer.cell.${k}`);
                  return (
                    <td key={i} className={'cv-' + k} title={t('answer.cellTip', {name: m.name, concept: c, state})}>
                      <span aria-label={state}>{CELL_SYMBOL[k]}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="ov-legend">
          <span>
            <i className="cv-on">●</i> {t('answer.legend.on')}
          </span>
          <span>
            <i className="cv-long">◐</i> {t('answer.legend.long')}
          </span>
          <span>
            <i className="cv-off">○</i> {t('answer.legend.off')}
          </span>
          {concepts.length > SHOWN_CONCEPTS ? (
            <span className="faint">{t('answer.moreConcepts', {count: concepts.length - SHOWN_CONCEPTS})}</span>
          ) : null}
        </div>
      </div>
    </SideCard>
  );
}

/** The headline is the find itself: the verdict, the best table large, the others one line each. */
function FoundBlock({answer}: {answer: AnalysisAnswer}) {
  const {t, jumpTo} = useShared();
  const [icon, wordKey] = VERDICT_WORD[answer.verdict] ?? ['', ''];
  const objects = answer.objects;
  const best = objects[0];
  const verdict = (
    <div className="ans-verdict">
      <span className="av-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="av-word">{wordKey ? t(wordKey) : answer.verdict}</span>
      {answer.missing.length ? (
        <span className="av-miss" title={t('answer.missingTip')}>
          {t('answer.missing', {items: answer.missing.join(', ')})}
        </span>
      ) : null}
      <span className="av-for">
        {objects.length ? t('answer.suggested', {count: objects.length}) : t('answer.noneAboveThreshold')}
      </span>
    </div>
  );
  if (!best) return verdict;
  return (
    <>
      {verdict}
      <button
        className={'ans-best lc-' + best.level}
        type="button"
        onClick={() => jumpTo(best)}
        title={t('answer.openDetail', {key: best.key})}
      >
        <Ring m={best} />
        <span className="ab-text">
          <span className="ab-k">{t('answer.best')}</span>
          <span className="ab-name">
            <Breakable name={best.name} />
            <ApprovedMark m={best} />
          </span>
          {best.covers ? <span className="ab-covers">{best.covers}</span> : null}
          <span className="ab-path">
            {`${best.database}.${best.schema}` + (best.groups.length ? ' · ' + best.groups[0] : '')}
          </span>
        </span>
      </button>
      {objects.length > 1 ? (
        <ol className="ans-also" start={2}>
          {objects.slice(1).map((m) => (
            <li key={m.key}>
              <button
                className={'aa-row lc-' + m.level}
                type="button"
                onClick={() => jumpTo(m)}
                title={t('answer.alsoTip', {key: m.key, score: pct(m.score), level: m.level})}
              >
                <span className="aa-n">{m.rank}</span>
                <span className="aa-name">
                  {m.name}
                  <ApprovedMark m={m} />
                </span>
                <span className="aa-covers">{m.covers || ''}</span>
                <span className="aa-pct">{'%' + pct(m.score)}</span>
              </button>
            </li>
          ))}
        </ol>
      ) : null}
    </>
  );
}

function ConceptChip({concept}: {concept: string}) {
  const {cls, prefix, label} = conceptParts(concept);
  return (
    <span className={'chip ' + cls}>
      {prefix}
      <b>{label}</b>
    </span>
  );
}

interface Props {
  answer: AnalysisAnswer;
  /** "↻ Yeniden analiz et": a new analysis without the kept answer. */
  onRedo: () => void;
  /** "⬇ Excel raporu" through the shared client. */
  onReport: () => void;
  /** The report's address, shown on the link; the download itself goes through `onReport`. */
  reportHref: string;
  openTable?: (key: string) => void;
  hasTable?: (key: string) => boolean;
}

/** The whole answer: the head with the find, the suggestions and the guide column. */
export function AnswerView({answer: r, onRedo, onReport, reportHref, openTable, hasTable}: Props) {
  const {t} = useIntl();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [nearKey, setNearKey] = useState<string | null>(null);
  const [rejectedKey, setRejectedKey] = useState<string | null>(null);
  const [flash, setFlash] = useState<{key: string; at: number} | null>(null);
  const rich = useMemo(() => richTokenizer(r), [r]);

  // A link to a suggestion opens its row and brings it into view; the rest stays put.
  useEffect(() => {
    if (flash === null) return;
    const el = document.getElementById(cardId(flash.key));
    if (!el) return;
    const from = window.scrollY;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'nearest'});
    // Some browsers drop a smooth scroll (busy page, background tab): then jump.
    const timer = window.setTimeout(() => {
      const box = el.getBoundingClientRect();
      if (window.scrollY === from && (box.top < 90 || box.top > window.innerHeight - 60)) el.scrollIntoView({block: 'start'});
    }, 250);
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
    return () => window.clearTimeout(timer);
  }, [flash]);

  const feedback = r.feedback ?? null;
  const shared: Shared = useMemo(
    () => ({
      t,
      rich,
      openTable,
      hasTable,
      jumpTo: (m: AnswerObject) => {
        setOpenKey(m.key);
        setFlash({key: m.key, at: performance.now()});
      },
      // The question and the time the answer was written go back with every vote (Decision 4).
      vote:
        ({scope, table_key}) =>
        (vote, note) =>
          VoteService.cast({
            query: r.query,
            scope,
            ...(table_key ? {table_key} : {}),
            vote,
            ...(note ? {note} : {}),
            ...(feedback?.answer_at ? {answer_at: feedback.answer_at} : {}),
          }),
      mine: feedback?.mine ?? {},
    }),
    [t, rich, openTable, hasTable, r.query, feedback],
  );

  const [title, lead] = splitSummary(r.summary);
  const rejected = r.rejected ?? [];
  const endorsed = r.endorsed ?? [];
  const why = r.fallback ? r.fallback.replace(/\.?$/, '.') : t('answer.unavailableNoModel');
  const ruleNote = t('answer.unavailableNote', {why});
  const ruleShort = t('answer.unavailableShort', {why: r.fallback || t('answer.unavailableShortNoModel')});
  const meta =
    t('answer.meta', {seconds: (r.elapsed_ms / 1000).toFixed(1), version: r.dictionary_version}) +
    (r.llm_model ? t('answer.metaModel', {model: r.llm_model}) : '');

  const glance = <Overview answer={r} />;
  const hasGlance = r.objects.length > 0 && answerConcepts(r.objects).length > 0;
  const plan = r.design.length ? (
    <SideCard title={t('answer.plan')} cls="plan" count={r.design.length}>
      <ol className="steps">
        {r.design.map((x, i) => (
          <li key={i}>
            <Rich text={x} />
          </li>
        ))}
      </ol>
    </SideCard>
  ) : null;
  const watch = r.attention.length ? (
    <SideCard title={t('answer.watch')} cls="warn" count={r.attention.length}>
      <ul className="watch">
        {r.attention.map((x, i) => (
          <li key={i}>
            <Rich text={x} />
          </li>
        ))}
      </ul>
    </SideCard>
  ) : null;
  const notes =
    r.analyst && r.notes.length ? (
      <SideCard title={t('answer.notes')} cls="notes" count={r.notes.length}>
        <ul className="note-list">
          {r.notes.map((n, i) => (
            <li key={i} className={'nt ' + (NOTE_TONE[n.scope] ?? '')}>
              <details>
                <summary>
                  <span className="nt-tag">{n.scope}</span>
                  <b>
                    <Rich text={n.title} />
                  </b>
                </summary>
                <div>
                  <Rich text={n.text} />
                </div>
              </details>
            </li>
          ))}
        </ul>
      </SideCard>
    ) : null;
  const hasSide = hasGlance || plan !== null || watch !== null || notes !== null;

  const reused = r.reused;
  const reusedTip = reused
    ? reused.match === 'aynı soru'
      ? t('answer.reusedSame', {at: reused.at})
      : t('answer.reusedMeaning', {query: reused.query, at: reused.at})
    : '';

  return (
    <AnswerContext.Provider value={shared}>
      <div className={'ans ' + verdictClass(r.verdict)}>
        <section className="answer ans-head">
          <div className="answer-top">
            <span className="vbadge">{r.verdict}</span>
            {r.analyst ? (
              <span className="src ai" title={t('answer.analystTip')}>
                {t('answer.analyst', {model: r.llm_model.split('/').pop() ?? r.llm_model})}
              </span>
            ) : (
              <span className="src rule" title={ruleNote}>
                {t('answer.unavailable')}
              </span>
            )}
            {reused ? (
              <span className="src reused" title={reusedTip}>
                {t('answer.reused', {date: reused.at.slice(0, 10)})}
              </span>
            ) : null}
            <span className="answer-q" title={r.query}>
              {r.query}
            </span>
            {reused ? (
              <button className="redo" title={t('answer.redoTip')} onClick={onRedo}>
                {t('answer.redo')}
              </button>
            ) : null}
            <a
              className="dl"
              href={reportHref}
              download=""
              onClick={(event) => {
                event.preventDefault();
                onReport();
              }}
            >
              {t('answer.report')}
            </a>
          </div>
          <div className="ans-hero">
            <div className="ans-text">
              <FoundBlock answer={r} />
              <details className="ans-why">
                <summary>
                  <span className="aw-k">{t('answer.summary')}</span>
                  <span className="aw-peek">{title}</span>
                </summary>
                <p className="ans-title">
                  <Rich text={title} />
                </p>
                {lead ? (
                  <p className="ans-lead">
                    <Rich text={lead} />
                  </p>
                ) : null}
                {r.interpretation ? (
                  <p className="ans-read">
                    <span className="ans-read-k">{t('answer.request')}</span>
                    <span>
                      <Rich text={r.interpretation} />
                    </span>
                  </p>
                ) : null}
              </details>
              {r.analyst ? null : (
                <div className="answer-fallback" title={ruleNote}>
                  {ruleShort}
                </div>
              )}
              {r.reused && feedback?.answer_rejected ? (
                <div className="answer-fallback">{t('vote.keptRejected')}</div>
              ) : null}
            </div>
          </div>
        </section>
        <div className={'ans-grid' + (hasSide ? '' : ' solo')}>
          <div className="ans-main">
            {r.objects.length ? <PickList items={r.objects} openKey={openKey} onOpen={setOpenKey} /> : null}
            {!r.objects.length ? <div className="empty">{t('answer.empty')}</div> : null}
            {r.near.length ? (
              <details className="ask-more">
                <summary>{t('answer.near', {count: r.near.length})}</summary>
                <PickList items={r.near} aside className="inner pick-list" openKey={nearKey} onOpen={setNearKey} />
              </details>
            ) : null}
            {endorsed.length ? (
              <section className="guide crowd">
                <div className="label">{t('vote.endorsed')}</div>
                <div className="crowd-list">
                  {endorsed.map((e) => (
                    <button
                      key={e.key}
                      className="crowd-item"
                      type="button"
                      title={t('vote.endorsedTip')}
                      onClick={(event) => {
                        event.stopPropagation();
                        openTable?.(e.key);
                      }}
                    >
                      <b>
                        <Breakable name={e.name} />
                      </b>
                      <span>{e.schema}</span>
                      <span className="vb up">{t('vote.endorsedCount', {count: e.votes.up})}</span>
                    </button>
                  ))}
                </div>
              </section>
            ) : null}
            {rejected.length ? (
              <details className="ask-more">
                <summary>{t('vote.rejected', {count: rejected.length})}</summary>
                <div className="inner">
                  <p className="faint">{t('vote.rejectedNote')}</p>
                  <PickList items={rejected} aside dim openKey={rejectedKey} onOpen={setRejectedKey} />
                </div>
              </details>
            ) : null}
            {r.objects.length || rejected.length ? (
              <AnswerVote
                answer={feedback?.answer ?? null}
                mine={feedback?.mine[''] ?? ''}
                send={shared.vote({scope: 'answer'})}
              />
            ) : null}
            <details className="ask-more">
              <summary>{t('answer.searchDetails')}</summary>
              <div className="inner">
                <div className="label">{t('answer.concepts')}</div>
                <div className="chips">
                  {r.concepts.map((c, i) => (
                    <ConceptChip key={i} concept={c} />
                  ))}
                  {r.expansion.length ? (
                    <span className="chip" title={r.expansion.join(', ')}>
                      {t('answer.expansion', {count: r.expansion.length})}
                    </span>
                  ) : null}
                </div>
                <div className="label">{t('answer.method')}</div>
                <ul className="method">
                  {r.method.map((x, i) => (
                    <li key={i} className="muted">
                      {x}
                    </li>
                  ))}
                </ul>
                <div className="faint">{meta}</div>
              </div>
            </details>
          </div>
          {hasSide ? (
            <aside className="ans-side" aria-label={t('answer.side')}>
              {hasGlance ? <div className="side-glance">{glance}</div> : null}
              {plan || watch || notes ? (
                <div className="side-guide">
                  {plan}
                  {watch}
                  {notes}
                </div>
              ) : null}
            </aside>
          ) : null}
        </div>
      </div>
    </AnswerContext.Provider>
  );
}
