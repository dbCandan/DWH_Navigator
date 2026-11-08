import {Link} from 'react-router';
import {useIntl} from '@/contexts/IntlContext';
import {
  callNumber,
  callOutcomeText,
  shownPhases,
  stepDetailText,
  tableName,
  treeOrder,
  withoutVerdict,
} from '@/lib/analysisRecords';
import {formatDuration, formatKilo, formatWhen} from '@/lib/format';
import type {RecordDetail} from '@/types/records';
import {analysisLlmCallsPath} from './nav';
import {FlowChip, VerdictBadge} from './RecordParts';

/** The step indent per tree level (admin.html timeline). */
const INDENT_PX = 14;

/** Who wrote the answer, in words (analysis-records Requirement 18; admin.html detail `by`). */
function writtenBy(record: RecordDetail, t: (key: string, values?: Record<string, string | number>) => string): string {
  const reuse = record.reused;
  if (record.flow === 'analyst') return t('records.by.analyst', {model: record.model});
  if (record.flow === 'reused') {
    if (!reuse) return t('records.flow.reused');
    const at = reuse.at ? formatWhen(reuse.at, t) : t('records.verdict.none');
    return reuse.match === 'same_question'
      ? t('records.by.sameQuestion', {at, model: record.model})
      : t('records.by.sameMeaning', {query: reuse.query, at, model: record.model});
  }
  return t(`records.by.${record.flow}`);
}

/**
 * The record's steps in tree order on one time axis (analysis-records Requirement 19; admin.html
 * timeline): indent by depth, the bar placed by start and length, "✕" before a failed step, the
 * tooltip with kind, times, tokens, a failed call's class and the detail.
 */
export function Timeline({record}: {record: RecordDetail}) {
  const {t} = useIntl();
  const ordered = treeOrder(record.steps);
  if (!ordered.length) return <p className="note">{t('records.timeline.none')}</p>;
  const total = Math.max(1, record.duration_ms ?? 0, ...record.steps.map((step) => step.start_ms + step.ms));
  const rows = ordered.map(([step, depth]) => {
    const left = (100 * step.start_ms) / total;
    const width = Math.max(0.3, (100 * step.ms) / total);
    const prompt = callNumber(step.call, 'prompt_tokens');
    const completion = callNumber(step.call, 'completion_tokens');
    const time =
      t('records.timeline.tipTime', {start: formatDuration(step.start_ms, t), duration: formatDuration(step.ms, t)}) +
      (prompt || completion
        ? ' · ' + t('records.timeline.tipTokens', {prompt: formatKilo(prompt, t), completion: formatKilo(completion, t)})
        : '');
    const detail = stepDetailText(step, t);
    const failure = step.kind === 'llm' && step.status === 'error' ? callOutcomeText(step.call, t) : '';
    const tip = [t('records.timeline.tipName', {name: step.name, kind: t(`records.timeline.kind.${step.kind}`)}), time, failure, detail]
      .filter(Boolean)
      .join('\n');
    const indent = {paddingLeft: `${depth * INDENT_PX}px`};
    return [
      <div className="nm" style={indent} title={tip} key={`n${step.seq}`}>
        {step.status === 'error' ? <span className="err">{t('records.timeline.error')}</span> : null}
        {step.name}
      </div>,
      <div className="lane" title={tip} key={`l${step.seq}`}>
        <i
          className={`bar ${step.kind}${step.status === 'error' ? ' error' : ''}`}
          style={{left: `${left.toFixed(2)}%`, width: `${Math.min(width, 100 - left).toFixed(2)}%`}}
        />
      </div>,
      <div className="ms" key={`m${step.seq}`}>
        {step.kind === 'event' && !step.ms ? t('records.timeline.eventMark') : formatDuration(step.ms, t)}
      </div>,
      detail && (step.status !== 'ok' || step.kind === 'step') ? (
        <div className="why" style={indent} title={detail} key={`w${step.seq}`}>
          {detail}
        </div>
      ) : null,
    ];
  });
  return (
    <div>
      <div className="legend" style={{margin: '4px 0 8px'}}>
        <span>
          <i style={{background: 'var(--k-step)'}} />
          {t('records.timeline.legendStep')}
        </span>
        <span>
          <i style={{background: 'var(--k-llm)'}} />
          {t('records.timeline.legendLlm')}
        </span>
        <span>
          <i style={{background: 'var(--warn)'}} />
          {t('records.timeline.legendWait')}
        </span>
      </div>
      <div className="wf">{rows}</div>
      {record.steps_truncated ? <p className="note">{t('records.timeline.truncated')}</p> : null}
    </div>
  );
}

/**
 * A record's drawer body (analysis-records Requirement 18; admin.html Analyses.detail): the
 * answer, the suggested tables, who wrote it, the list term, the model use, the reason or the
 * error, where the time went, the folded timeline and the keyboard hint.
 */
export function RecordDetailBody({record}: {record: RecordDetail}) {
  const {t} = useIntl();
  const phases = shownPhases(record.phases);
  const total = Math.max(1, record.duration_ms ?? 0);
  return (
    <>
      <dl className="kv">
        {record.summary ? (
          <>
            <dt>{t('records.detail.answer')}</dt>
            <dd>
              <VerdictBadge verdict={record.verdict} flow={record.flow} /> {withoutVerdict(record.summary)}
            </dd>
          </>
        ) : null}
        {record.table_keys.length ? (
          <>
            <dt>{t('records.detail.tables')}</dt>
            <dd>
              {record.table_keys.map((key) => (
                <span className="tag" title={key} style={{margin: '0 6px 4px 0'}} key={key}>
                  {tableName(key)}
                </span>
              ))}
            </dd>
          </>
        ) : null}
        <dt>{t('records.detail.by')}</dt>
        <dd>
          <FlowChip flow={record.flow} /> <span className="muted">{writtenBy(record, t)}</span>
        </dd>
        {record.origin === 'list' && record.list_file_name ? (
          <>
            <dt>{t('records.detail.list')}</dt>
            <dd>{t('records.detail.listValue', {file: record.list_file_name, position: record.list_position ?? ''})}</dd>
          </>
        ) : null}
        {record.llm_calls ? (
          <>
            <dt>{t('records.detail.usage')}</dt>
            <dd>
              <span>
                {t('records.detail.usageValue', {
                  calls: record.llm_calls,
                  prompt: formatKilo(record.prompt_tokens, t),
                  completion: formatKilo(record.completion_tokens, t),
                })}
              </span>{' '}
              <Link className="inline-link" to={analysisLlmCallsPath(record.public_id)}>
                {t('records.detail.usageCalls')}
              </Link>
            </dd>
          </>
        ) : null}
      </dl>
      {record.unavailable_reason ? <div className="msg warn">{t('records.detail.reason', {reason: record.unavailable_reason})}</div> : null}
      {record.error ? <div className="msg bad">{t('records.detail.error', {message: record.error.message})}</div> : null}
      {phases.length ? (
        <>
          <div className="sec-t">{t('records.detail.where', {duration: formatDuration(record.duration_ms, t)})}</div>
          <div className="stack">
            {phases.map((p) => (
              <i
                key={p.phase}
                className={'ph-' + p.cls}
                title={t('records.detail.phaseTip', {name: t(`records.phase.${p.phase}`), duration: formatDuration(p.ms, t)})}
                style={{width: `${Math.max(0.6, (100 * p.ms) / total).toFixed(2)}%`}}
              />
            ))}
          </div>
          <ul className="phases">
            {phases.map((p) => (
              <li key={p.phase}>
                <i className={'ph-' + p.cls} />
                {t(`records.phase.${p.phase}`)}
                <span>{formatDuration(p.ms, t)}</span>
                {p.note ? <small>{t(`records.phase.${p.phase}.note`)}</small> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <details className="fold">
        <summary>{t('records.detail.timeline')}</summary>
        <Timeline record={record} />
      </details>
      <div className="note" style={{marginTop: '10px'}}>
        {t('records.detail.keys')}
      </div>
    </>
  );
}
