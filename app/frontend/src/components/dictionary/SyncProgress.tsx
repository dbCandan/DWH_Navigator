import {useIntl} from '@/contexts/IntlContext';
import {runPercent} from '@/lib/dictionarySync';
import {formatNumber} from '@/lib/format';
import type {SyncRunSummary} from '@/types/dictionarySync';

/** The running run's phase and work done (dictionary-sync Requirement 2). */
export function SyncProgress({run, onDetails}: {run: SyncRunSummary; onDetails?: () => void}) {
  const {t} = useIntl();
  const percent = runPercent(run);
  const phase = t(`dictionary.sync.phase.${run.phase}`);
  return (
    <section className="card" id="d-progress" aria-live="polite">
      <div className="card-h">
        <h2>{t(run.kind === 'geri_donus' ? 'dictionary.sync.runningRestore' : 'dictionary.sync.running')}</h2>
        <span className="pill acc">{phase}</span>
        {onDetails ? (
          <button className="btn sm" type="button" onClick={onDetails}>
            {t('dictionary.update.details')}
          </button>
        ) : null}
        {percent === null ? null : (
          <span className="note">
            {t('dictionary.sync.progress', {done: formatNumber(run.progress_done), total: formatNumber(run.progress_total)})}
          </span>
        )}
      </div>
      {percent === null ? null : (
        <div className="stack" role="progressbar" aria-label={phase} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
          <i style={{width: `${percent}%`, background: 'var(--accent)'}} />
        </div>
      )}
      <p className="note">{t('dictionary.sync.leaveHint')}</p>
    </section>
  );
}
