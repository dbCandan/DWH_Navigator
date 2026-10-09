import {useIntl} from '@/contexts/IntlContext';
import {FLOW_CLASS, type Kpi} from '@/lib/analysisRecords';
import type {Flow, RecordRow} from '@/types/records';

/** The flow chip: mark and Turkish name, coloured by the source's class (admin.html flowChip). */
export function FlowChip({flow}: {flow: Flow}) {
  const {t} = useIntl();
  return (
    <span className={'flow ' + FLOW_CLASS[flow]}>
      {t(`records.flowMark.${flow}`)} {t(`records.flow.${flow}`)}
    </span>
  );
}

/** The verdict badge; without a verdict "durdu" for a stopped analysis, else "—" (admin.html verdictBadge). */
export function VerdictBadge({verdict, flow}: {verdict: RecordRow['verdict']; flow: Flow}) {
  const {t} = useIntl();
  if (!verdict)
    return <span className="vb none">{flow === 'cancelled' ? t('records.verdict.stopped') : t('records.verdict.none')}</span>;
  return <span className={'vb ' + verdict.split(' ')[0]}>{verdict}</span>;
}

/** The indicators' tiles; each tile's line is also its tooltip. */
export function KpiTiles({kpis}: {kpis: readonly Kpi[]}) {
  return (
    <>
      {kpis.map((kpi) => (
        <div className="kpi" title={kpi.s} key={kpi.k}>
          <div className="k">{kpi.k}</div>
          <div className="v">{kpi.v}</div>
          <div className="s">{kpi.s}</div>
        </div>
      ))}
    </>
  );
}
