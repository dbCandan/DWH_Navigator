import type {KeyboardEvent} from 'react';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {RUNS_PAGE_SIZE} from '@/hooks/useDictionarySync';
import {versionDigits} from '@/lib/adminStatus';
import {runPill} from '@/lib/dictionarySync';
import {formatDateTime, formatNumber} from '@/lib/format';
import type {SyncRunSummary} from '@/types/dictionarySync';
import {Pager} from './Pager';

interface Props {
  runs: SyncRunSummary[] | null;
  total: number;
  page: number;
  onPage: (page: number) => void;
  onOpen: (run: SyncRunSummary) => void;
}

/** The "Güncellemeler" list (dictionary-sync Requirement 9): a row opens the run's report. */
export function RunHistory({runs, total, page, onPage, onOpen}: Props) {
  const {t} = useIntl();
  const keyDown = (run: SyncRunSummary) => (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(run);
    }
  };
  return (
    <section className="card" id="d-runs">
      <h2>{t('dictionary.runs.title')}</h2>
      {runs === null ? (
        <Skeleton />
      ) : runs.length ? (
        <>
          <table className="t">
            <thead>
              <tr>
                <th>{t('dictionary.runs.started')}</th>
                <th>{t('dictionary.runs.kind')}</th>
                <th>{t('dictionary.runs.status')}</th>
                <th>{t('dictionary.runs.by')}</th>
                <th>{t('dictionary.runs.version')}</th>
                <th className="r">{t('dictionary.runs.tables')}</th>
                <th className="r">{t('dictionary.runs.columns')}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const {counts} = run;
                return (
                  <tr key={run.public_id} className="click" tabIndex={0} onClick={() => onOpen(run)} onKeyDown={keyDown(run)}>
                    <td>{formatDateTime(run.started_at)}</td>
                    <td>{t(`dictionary.runs.kind.${run.kind}`)}</td>
                    <td>
                      <span className={runPill(run.status)}>{t(`dictionary.sync.status.${run.status}`)}</span>
                    </td>
                    <td>{run.started_by?.display_name ?? '—'}</td>
                    <td className="mono" title={run.new_version}>
                      {run.new_version ? versionDigits(run.new_version) : '—'}
                    </td>
                    <td className="r">
                      {t('dictionary.runs.delta', {
                        added: formatNumber(counts.tables_added),
                        removed: formatNumber(counts.tables_removed),
                      })}
                    </td>
                    <td className="r">
                      {t('dictionary.runs.delta', {
                        added: formatNumber(counts.columns_added),
                        removed: formatNumber(counts.columns_removed),
                      })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <Pager page={page} pageSize={RUNS_PAGE_SIZE} total={total} onPage={onPage} />
        </>
      ) : (
        <p className="empty">{t('dictionary.runs.empty')}</p>
      )}
    </section>
  );
}
