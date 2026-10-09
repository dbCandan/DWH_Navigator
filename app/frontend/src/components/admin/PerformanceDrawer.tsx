import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {PHASES} from '@/lib/analysisRecords';
import {formatDuration, formatKilo, formatNumber} from '@/lib/format';
import type {RecordSummary} from '@/types/records';
import {Drawer} from './Drawer';

interface Props {
  /** The period's name ("Son 7 gün"). */
  period: string;
  /** The filter's summary; null while it loads. */
  summary: RecordSummary | null;
  /** A person was clicked: the page filters by them and closes the drawer. */
  onPick: (askerPublicId: string) => void;
  onClose: () => void;
}

/**
 * "Performans" (analysis-records Requirement 21; admin.html Analyses.perf): the average time per
 * phase, the spread of durations, the model use and the people asking, for the page's filter.
 */
export function PerformanceDrawer({period, summary, onPick, onClose}: Props) {
  const {t} = useIntl();
  const count = summary?.count ?? 0;
  const phases = summary
    ? PHASES.map((p) => ({...p, average: summary.phases.find((x) => x.phase === p.phase)})).filter(
        (p): p is typeof p & {average: {average_ms: number; count: number}} =>
          Boolean(p.average && p.average.count && p.average.average_ms !== null),
      )
    : [];
  const maxAverage = Math.max(1, ...phases.map((p) => p.average.average_ms));
  return (
    <Drawer
      title={t('records.perf.title')}
      sub={t('records.perf.sub', {period, count: formatNumber(count)})}
      onClose={onClose}
    >
      {!summary ? (
        <Skeleton />
      ) : !count ? (
        <p className="empty">{t('records.perf.empty')}</p>
      ) : (
        <>
          <div className="sec-t">{t('records.perf.phases')}</div>
          <div className="hbars">
            {phases.map((p) => [
              <div key={p.phase + 'n'}>{t(`records.phase.${p.phase}`)}</div>,
              <div className="tr" title={t('records.perf.phaseCount', {count: formatNumber(p.average.count)})} key={p.phase + 't'}>
                <i style={{width: `${((100 * p.average.average_ms) / maxAverage).toFixed(1)}%`}} />
              </div>,
              <div className="v" key={p.phase + 'v'}>
                {formatDuration(p.average.average_ms, t)}
              </div>,
            ])}
          </div>
          <p className="note">
            {t('records.perf.spread', {
              p50: formatDuration(summary.p50_ms, t),
              p90: formatDuration(summary.p90_ms, t),
              max: formatDuration(summary.max_ms, t),
            })}
          </p>
          <div className="sec-t">{t('records.perf.usage')}</div>
          <p>
            {summary.llm_calls
              ? t('records.perf.usageValue', {
                  calls: formatNumber(summary.llm_calls),
                  prompt: formatKilo(summary.prompt_tokens, t),
                  completion: formatKilo(summary.completion_tokens, t),
                })
              : t('records.perf.usageNone')}
          </p>
          <div className="sec-t">{t('records.perf.users')}</div>
          <table className="t">
            <tbody>
              {summary.askers.map((asker) => (
                <tr
                  className="click"
                  key={asker.public_id}
                  tabIndex={0}
                  onClick={() => onPick(asker.public_id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onPick(asker.public_id);
                    }
                  }}
                >
                  <td>{asker.display_name}</td>
                  <td className="r">{t('records.perf.userCount', {count: formatNumber(asker.count)})}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Drawer>
  );
}
