import {useCallback, useEffect, useState, type ReactNode} from 'react';
import {Link} from 'react-router';
import {Icon, type IconName} from '@/components/admin/Icon';
import {adminPath, analysisPath} from '@/components/admin/nav';
import {PageHead} from '@/components/admin/PageHead';
import {FlowChip, KpiTiles, VerdictBadge} from '@/components/admin/RecordParts';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useIndexRebuild} from '@/hooks/useAdminActions';
import {useDictionaryState} from '@/hooks/useDictionaryState';
import {useLlmState} from '@/hooks/useLlmState';
import {useSearchState} from '@/hooks/useSearchState';
import {dictionaryStatus, indexStatus} from '@/lib/adminStatus';
import {recordKpis} from '@/lib/analysisRecords';
import {formatDateTime, formatNumber, formatWhen} from '@/lib/format';
import {modelStatus} from '@/lib/modelStatus';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {SavedAnswersService} from '@/services/savedAnswers';
import type {SavedAnswersSummary} from '@/types/analysis';
import type {DayCount, RecordPage, RecordSummary} from '@/types/records';

/** A source of the page: read, or unreadable (its card then shows "…"). */
type Source<T> = {state: 'ok'; value: T} | {state: 'failed'};

async function read<T>(run: () => Promise<T>): Promise<Source<T>> {
  try {
    return {state: 'ok', value: await run()};
  } catch {
    return {state: 'failed'};
  }
}

const value = <T,>(source: Source<T>): T | null => (source.state === 'ok' ? source.value : null);

const RECENT = 100;
const CHART_DAYS = 14;

interface Sources {
  week: Source<RecordSummary>;
  days: Source<{days: DayCount[]}>;
  recent: Source<RecordPage>;
  answers: Source<SavedAnswersSummary>;
}

function readAll(): Promise<Sources> {
  return Promise.all([
    read(() => AnalysisRecordsService.summary({period: '7d'})),
    read(() => AnalysisRecordsService.dailyCounts(CHART_DAYS)),
    read(() => AnalysisRecordsService.list({period: 'all'}, 1, undefined, RECENT)),
    read(() => SavedAnswersService.summary()),
  ]).then(([week, days, recent, answers]) => ({week, days, recent, answers}));
}

/** A health card (admin.html PAGES.genel card()): state colour, icon, title, value, line, button. */
function HealthCard(props: {cls: string; icon: IconName; title: string; value: string; line: string; children?: ReactNode}) {
  return (
    <div className={'hc ' + props.cls}>
      <div className="k">
        <Icon name={props.icon} />
        {props.title}
      </div>
      <div className="v">{props.value}</div>
      <div className="s">{props.line}</div>
      {props.children}
    </div>
  );
}

/** "dd.mm" of a `YYYY-MM-DD` day. */
function dayLabel(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('tr-TR', {day: '2-digit', month: '2-digit'});
}

/** The last 14 days as stacked bars: tables suggested, and not (admin.html PAGES.genel activity). */
function DayChart({days}: {days: readonly DayCount[]}) {
  const {t} = useIntl();
  const W = 700;
  const H = 150;
  const bw = W / Math.max(1, days.length);
  const max = Math.max(1, ...days.map((day) => day.with_tables + day.without_tables));
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('overview.chart.label')}>
      {days.map((day, i) => {
        const hOk = ((H - 26) * day.with_tables) / max;
        const hNo = ((H - 26) * day.without_tables) / max;
        const x = i * bw + bw * 0.18;
        const w = bw * 0.64;
        const label = dayLabel(day.date);
        return (
          <g key={day.date}>
            <title>
              {t('overview.chart.tip', {
                date: label,
                total: day.with_tables + day.without_tables,
                ok: day.with_tables,
                no: day.without_tables,
              })}
            </title>
            <rect className="bar-no" x={x} y={H - 18 - hNo} width={w} height={hNo} rx={3} />
            <rect className="bar-ok" x={x} y={H - 18 - hNo - hOk} width={w} height={hOk} rx={3} />
            {i % 2 === 1 ? (
              <text x={x + w / 2} y={H - 4} textAnchor="middle">
                {label}
              </text>
            ) : null}
          </g>
        );
      })}
      <line className="base" x1={0} x2={W} y1={H - 18} y2={H - 18} />
    </svg>
  );
}

/**
 * The "Genel bakış" page (analysis-records Requirement 13-15; admin.html PAGES.genel): the
 * first-run steps while any is left, the four health cards, the last 7 days' indicators with the
 * 14-day chart, and the newest questions. A source that cannot be read shows "…" on its card only.
 */
export default function OverviewPage() {
  const {t} = useIntl();
  const {llm, failure: llmFailure} = useLlmState();
  const {dictionary, failure: dictionaryFailure} = useDictionaryState();
  const {index} = useSearchState();
  const rebuild = useIndexRebuild();
  const [sources, setSources] = useState<Sources | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const label = t('admin.page.genel.label');

  useEffect(() => {
    let live = true;
    void readAll().then((answer) => live && setSources(answer));
    return () => {
      live = false;
    };
  }, []);

  const reload = useCallback(async () => setSources(await readAll()), []);

  async function runRebuild() {
    setRebuilding(true);
    try {
      await rebuild();
      await reload();
    } finally {
      setRebuilding(false);
    }
  }

  const head = <PageHead title={label} description={t('admin.page.genel.description')} />;
  const shellSettled = (llm !== null || llmFailure !== null) && (dictionary !== null || dictionaryFailure !== null);
  if (!sources || !shellSettled)
    return (
      <section className="page on" id="p-genel" aria-label={label}>
        {head}
        <Skeleton />
      </section>
    );

  const unknown = t('overview.unknown');
  const m = modelStatus(llm, t);
  const d = dictionaryStatus(dictionary);
  const ix = indexStatus(index);
  const answers = value(sources.answers);
  const recent = value(sources.recent);
  const week = value(sources.week);
  const days = value(sources.days);

  const steps = [
    {done: d.state !== 'none', title: 'overview.setup.dictionary', hint: 'overview.setup.dictionaryHint', to: adminPath('sozluk')},
    {done: m.state === 'ok', title: 'overview.setup.model', hint: 'overview.setup.modelHint', to: adminPath('yapay-zeka')},
    {done: Boolean(recent && recent.total > 0), title: 'overview.setup.question', hint: 'overview.setup.questionHint', to: '/'},
  ];
  const doneSteps = steps.filter((step) => step.done).length;

  const indexValue = {
    ok: 'overview.index.ok',
    building: 'overview.index.building',
    stale: 'overview.index.stale',
    empty: 'overview.index.empty',
    unknown: 'overview.unknown',
  }[ix];
  const indexLine =
    index === null
      ? ''
      : ix === 'stale' && index.stale_inputs.length
        ? t('overview.index.changed', {inputs: index.stale_inputs.map((input) => t(`maintenance.input.${input}`)).join(', ')})
        : ix === 'empty'
          ? t('overview.index.emptyLine')
          : (ix === 'ok' || ix === 'building') && index.built_at
            ? t('overview.index.built', {when: formatWhen(index.built_at, t)})
            : '';

  return (
    <section className="page on" id="p-genel" aria-label={label}>
      {head}
      {doneSteps < steps.length ? (
        <section className="card setup">
          <div className="card-h">
            <h2>{t('overview.setup.title')}</h2>
            <span className="pill acc">{t('overview.setup.progress', {done: doneSteps})}</span>
          </div>
          <ol className="steps">
            {steps.map((step, i) => (
              <li className={step.done ? 'done' : ''} key={step.title}>
                <span className="n">{step.done ? '✓' : String(i + 1)}</span>
                <div className="tx">
                  <b>{t(step.title)}</b>
                  <small>{t(step.hint)}</small>
                </div>
                {step.done ? null : step.to === '/' ? (
                  <a className="btn sm" href="/">
                    {t('overview.setup.go')}
                    <Icon name="arrow" />
                  </a>
                ) : (
                  <Link className="btn sm" to={step.to}>
                    {t('overview.setup.go')}
                    <Icon name="arrow" />
                  </Link>
                )}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <div className="health">
        <HealthCard
          cls={m.state === 'ok' ? 'ok' : m.state === 'down' ? 'bad' : m.state === 'none' ? 'warn' : ''}
          icon="spark"
          title={t('overview.model.title')}
          value={m.state === 'unknown' ? unknown : m.state === 'none' ? t('overview.model.none') : m.label}
          line={
            m.state === 'ok'
              ? t('overview.model.ok', {detail: m.detail})
              : m.state === 'down'
                ? t('overview.model.down', {reason: m.detail})
                : m.state === 'none'
                  ? t('overview.model.noneLine')
                  : ''
          }
        >
          <Link className="btn sm" to={adminPath('yapay-zeka')}>
            {m.state === 'ok' ? t('overview.model.connections') : t('overview.model.connect')}
            <Icon name="arrow" />
          </Link>
        </HealthCard>
        <HealthCard
          cls={d.state === 'ok' ? 'ok' : d.state === 'none' || d.state === 'stale' ? 'warn' : ''}
          icon="book"
          title={t('overview.dictionary.title')}
          value={
            d.active
              ? t('overview.dictionary.value', {count: formatNumber(d.active.object_count)})
              : d.state === 'none'
                ? t('overview.dictionary.none')
                : unknown
          }
          line={
            d.active
              ? t('overview.dictionary.line', {
                  columns: formatNumber(d.active.column_count),
                  source: d.active.source_name,
                  at: formatDateTime(d.active.imported_at),
                })
              : d.state === 'none'
                ? t('overview.dictionary.noneLine')
                : ''
          }
        >
          <Link className="btn sm" to={adminPath('sozluk')}>
            {d.state === 'none' ? t('overview.dictionary.connect') : t('overview.dictionary.open')}
            <Icon name="arrow" />
          </Link>
        </HealthCard>
        <HealthCard
          cls={ix === 'ok' ? 'ok' : ix === 'unknown' ? '' : 'warn'}
          icon="layers"
          title={t('overview.index.title')}
          value={t(indexValue)}
          line={indexLine}
        >
          {ix === 'stale' ? (
            <button className="btn sm primary" type="button" disabled={rebuilding} onClick={() => void runRebuild()}>
              {rebuilding ? (
                t('overview.index.rebuilding')
              ) : (
                <>
                  <Icon name="refresh" />
                  {t('overview.index.rebuild')}
                </>
              )}
            </button>
          ) : null}
        </HealthCard>
        <HealthCard
          cls={answers?.usable ? 'ok' : ''}
          icon="clock"
          title={t('overview.answers.title')}
          value={answers ? t('overview.answers.value', {count: formatNumber(answers.usable)}) : unknown}
          line={
            answers
              ? answers.total
                ? t('overview.answers.line', {total: formatNumber(answers.total)})
                : t('overview.answers.none')
              : ''
          }
        >
          <Link className="btn sm" to={adminPath('bakim')}>
            {t('overview.answers.manage')}
            <Icon name="arrow" />
          </Link>
        </HealthCard>
      </div>
      <div className="grid g2 fill">
        <section className="card">
          <div className="card-h">
            <h2>{t('overview.week.title')}</h2>
            <Link className="btn sm ghost" to={adminPath('analizler')}>
              {t('overview.week.all')}
              <Icon name="arrow" />
            </Link>
          </div>
          <div className="kpis">
            {week ? (
              <KpiTiles kpis={recordKpis(week, t)} />
            ) : (
              <div className="kpi">
                <div className="v">{unknown}</div>
              </div>
            )}
          </div>
          {days ? <DayChart days={days.days} /> : <p className="empty">{unknown}</p>}
          <div className="legend">
            <span>
              <i style={{background: 'linear-gradient(0deg, var(--violet), var(--cyan))'}} />
              {t('overview.chart.legendOk')}
            </span>
            <span>
              <i style={{background: 'var(--coral-a55)'}} />
              {t('overview.chart.legendNo')}
            </span>
            <span>{t('overview.chart.legendSpan')}</span>
          </div>
        </section>
        <section className="card">
          <div className="card-h">
            <h2>{t('overview.recent.title')}</h2>
          </div>
          {recent === null ? (
            <p className="empty">{unknown}</p>
          ) : recent.items.length ? (
            <ul className="recent scroll">
              {recent.items.map((row) => (
                <li key={row.public_id}>
                  <Link to={analysisPath(row.public_id)}>
                    <span className="w">{formatWhen(row.asked_at, t).replace(t('common.when.today', {time: ''}), '')}</span>
                    <span className="q" title={row.query}>
                      <VerdictBadge verdict={row.verdict} flow={row.flow} />
                      {row.query}
                    </span>
                    <FlowChip flow={row.flow} />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">{t('overview.recent.empty')}</p>
          )}
        </section>
      </div>
    </section>
  );
}
