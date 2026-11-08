import {useEffect, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {useIntl} from '@/contexts/IntlContext';
import {runPill} from '@/lib/dictionarySync';
import {formatNumber} from '@/lib/format';
import type {SyncPreview, SyncRunPhase, SyncRunSummary} from '@/types/dictionarySync';
import {Fact} from './Fact';

/** The update's steps in the order the server runs them. */
const UPDATE_STEPS: readonly SyncRunPhase[] = [
  'reading',
  'comparing',
  'filling',
  'describing',
  'verifying',
  'scoring',
  'indexing',
];

/** What the preview reads and computes while the window waits for it. */
const PREVIEW_STEPS = ['dictionary.update.previewStep.read', 'dictionary.update.previewStep.compare', 'dictionary.update.previewStep.scope'];

const duration = (seconds: number) =>
  seconds < 90 ? `${formatNumber(seconds)} sn` : `${formatNumber(Math.round(seconds / 60))} dk`;

/** Seconds since `since` (an ISO time, or a moment in ms), counted every second while shown. */
function useElapsed(since: string | number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  if (since === null) return 0;
  const start = typeof since === 'number' ? since : Date.parse(since);
  return Math.max(0, Math.round((now - start) / 1000));
}

type StepState = 'done' | 'current' | 'waiting' | 'failed';

function stepStates(run: SyncRunSummary): StepState[] {
  const at = UPDATE_STEPS.indexOf(run.phase);
  const ended = run.status !== 'running';
  const failed = run.status === 'failed' || run.status === 'interrupted';
  return UPDATE_STEPS.map((_, index) => {
    if (ended && !failed) return 'done';
    if (at === -1) return ended ? 'done' : 'waiting';
    if (index < at) return 'done';
    if (index === at) return failed ? 'failed' : 'current';
    return 'waiting';
  });
}

const MARK: Record<StepState, string> = {done: '✓', current: '…', waiting: '·', failed: '✕'};

function RunSteps({run}: {run: SyncRunSummary}) {
  const {t} = useIntl();
  const states = stepStates(run);
  const elapsed = useElapsed(run.status === 'running' ? run.started_at : null);
  return (
    <>
      <div className="info">
        <Fact label={t('dictionary.report.result')} value={<span className={runPill(run.status)}>{t(`dictionary.sync.status.${run.status}`)}</span>} />
        {run.status === 'running' ? <Fact label={t('dictionary.update.elapsed')} value={duration(elapsed)} /> : null}
        {run.model ? <Fact label={t('dictionary.report.model')} value={run.model} /> : null}
      </div>
      <ol className="update-steps" aria-label={t('dictionary.update.steps')}>
        {UPDATE_STEPS.map((phase, index) => {
          const state = states[index];
          const counts = state === 'current' && run.progress_total > 0;
          return (
            <li key={phase} className={`step ${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="mark" aria-hidden="true">
                {MARK[state]}
              </span>
              <span className="what">
                <b>{t(`dictionary.sync.phase.${phase}`)}</b>
                <span className="sub2">{t(`dictionary.update.stepHint.${phase}`)}</span>
              </span>
              {counts ? (
                <span className="note">
                  {t('dictionary.sync.progress', {done: formatNumber(run.progress_done), total: formatNumber(run.progress_total)})}
                </span>
              ) : null}
              <span className="sr-only">{t(`dictionary.update.state.${state}`)}</span>
            </li>
          );
        })}
      </ol>
      {run.status === 'running' ? <p className="note">{t('dictionary.update.closeHint')}</p> : null}
      {run.error_message ? <div className="msg bad">{run.error_message}</div> : null}
    </>
  );
}

interface Props {
  /** The preview, null while it is being prepared. */
  preview: SyncPreview | null;
  previewFailure: string;
  /** The run this window follows: the running one, or the one that just ended. */
  run: SyncRunSummary | null;
  /** When the preview was asked for (ms), for its elapsed time. */
  previewSince: number | null;
  busy: boolean;
  onStart: () => void;
  onRetry: () => void;
  onOpenReport: (runId: string) => void;
  onClose: () => void;
}

/**
 * The update window: it opens at once on "Güncelle". First the preview — what is being read while
 * it is prepared, then what the update would look at — and after "Başlat" the run's steps, live.
 * Closing it stops nothing: the run goes on on the server, and the page's progress card opens the
 * window again.
 */
export function UpdateDrawer({preview, previewFailure, run, previewSince, busy, onStart, onRetry, onOpenReport, onClose}: Props) {
  const {t} = useIntl();
  const waiting = run === null && preview === null && !previewFailure;
  const elapsed = useElapsed(waiting ? previewSince : null);
  const ended = run !== null && run.status !== 'running';

  let foot = null;
  if (run === null && preview && !previewFailure) {
    foot = (
      <>
        <button className="btn" type="button" onClick={onClose}>
          {t('dictionary.edit.cancel')}
        </button>
        <button className="btn primary" type="button" disabled={busy || !preview.has_changes} onClick={onStart}>
          {t('dictionary.preview.start')}
        </button>
      </>
    );
  } else if (previewFailure && run === null) {
    foot = (
      <button className="btn" type="button" onClick={onRetry}>
        {t('dictionary.update.retry')}
      </button>
    );
  } else if (ended && run) {
    foot = (
      <button className="btn primary" type="button" onClick={() => onOpenReport(run.public_id)}>
        {t('dictionary.sync.openReport')}
      </button>
    );
  } else if (run) {
    foot = (
      <button className="btn" type="button" onClick={onClose}>
        {t('dictionary.update.hide')}
      </button>
    );
  }

  return (
    <Drawer title={t('dictionary.update.title')} sub={run ? t('dictionary.update.subRun') : t('dictionary.preview.title')} onClose={onClose} foot={foot}>
      <div aria-live="polite">
        {run ? (
          <RunSteps run={run} />
        ) : previewFailure ? (
          <div className="msg bad">{previewFailure}</div>
        ) : preview === null ? (
          <section id="d-preview-wait">
            <p>
              <b>{t('dictionary.update.preparing')}</b> <span className="note">{duration(elapsed)}</span>
            </p>
            <ol className="update-steps">
              {PREVIEW_STEPS.map((key) => (
                <li key={key} className="step current">
                  <span className="mark" aria-hidden="true">
                    …
                  </span>
                  <span className="what">{t(key)}</span>
                </li>
              ))}
            </ol>
            <p className="note">{t('dictionary.update.previewHint')}</p>
          </section>
        ) : (
          <section id="d-preview" aria-label={t('dictionary.preview.title')}>
            {preview.has_changes ? (
              <div className="info">
                <Fact label={t('dictionary.preview.tables')} value={formatNumber(preview.tables_needing_model)} />
                <Fact label={t('dictionary.preview.rows')} value={formatNumber(preview.rows_to_describe)} />
                <Fact label={t('dictionary.preview.codeChanged')} value={formatNumber(preview.scope.scope_code_changed ?? 0)} />
                <Fact label={t('dictionary.preview.calls')} value={formatNumber(preview.model_calls)} />
                <Fact label={t('dictionary.preview.duration')} value={duration(preview.estimated_seconds)} />
              </div>
            ) : (
              <div className="msg ok">{t('dictionary.preview.noChange')}</div>
            )}
            {preview.requires_approval && preview.has_changes ? <p className="note">{t('dictionary.preview.approval')}</p> : null}
          </section>
        )}
      </div>
    </Drawer>
  );
}
