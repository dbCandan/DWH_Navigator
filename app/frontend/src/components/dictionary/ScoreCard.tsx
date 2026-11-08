import {useIntl} from '@/contexts/IntlContext';
import {formatNumber} from '@/lib/format';
import type {SyncJudgedRow, SyncScore} from '@/types/dictionarySync';
import {Fact} from './Fact';

const VERDICT_PILL: Record<string, string> = {
  onaylanabilir: 'pill ok',
  incelenmeli: 'pill warn',
  reddedilmeli: 'pill bad',
};

const percent = (value: number) => `%${formatNumber(Math.round(value * 1000) / 10)}`;

interface Props {
  score: SyncScore;
  /** The run waits for approval: a misleading row can be fixed from here. */
  editable: boolean;
  onFix: (row: SyncJudgedRow) => void;
}

/**
 * The score card an admin decides on (dictionary_curation.score): the score and recommendation,
 * the mechanical checks with examples, the verifier's sample with its interval and the rows it
 * found misleading, the model's failed calls and what the rules cleaned.
 */
export function ScoreCard({score, editable, onFix}: Props) {
  const {t} = useIntl();
  if (score.score === undefined || !score.verdict) return null;
  const judge = score.judge;
  const failed = score.failed_checks ?? [];
  return (
    <section id="d-score" aria-label={t('dictionary.score.title')}>
      <h3>{t('dictionary.score.title')}</h3>
      <div className="info">
        <Fact label={t('dictionary.score.value')} value={<b>{formatNumber(score.score)}</b>} />
        <Fact
          label={t('dictionary.score.verdict')}
          value={<span className={VERDICT_PILL[score.verdict] ?? 'pill'}>{t(`dictionary.score.verdict.${score.verdict}`)}</span>}
        />
        {judge ? (
          <>
            <Fact
              label={t('dictionary.score.sample')}
              value={t('dictionary.score.sampleValue', {
                sample: formatNumber(judge.sample),
                population: formatNumber(judge.population),
              })}
            />
            <Fact
              label={t('dictionary.score.wrong')}
              value={t('dictionary.score.wrongValue', {
                wrong: formatNumber(judge.wrong),
                low: percent(judge.wrong_interval[0]),
                high: percent(judge.wrong_interval[1]),
              })}
            />
            <Fact label={t('dictionary.score.minor')} value={formatNumber(judge.minor)} />
          </>
        ) : (
          <Fact label={t('dictionary.score.sample')} value={t('dictionary.score.noJudge')} />
        )}
        {score.model ? (
          <Fact label={t('dictionary.score.modelFailures')} value={percent(score.model.failure_rate)} />
        ) : null}
        {score.rules ? (
          <Fact label={t('dictionary.score.normalized')} value={formatNumber(score.rules.normalized_fields)} />
        ) : null}
        {score.admin_edits ? <Fact label={t('dictionary.score.adminEdits')} value={formatNumber(score.admin_edits)} /> : null}
      </div>
      {failed.length ? (
        <div className="msg bad" id="d-score-checks">
          <b>{t('dictionary.score.failedChecks')}</b>
          <ul>
            {failed.map((name) => (
              <li key={name}>
                {t(`dictionary.score.check.${name}`)}: {formatNumber(score.checks?.[name]?.count ?? 0)}
                {score.checks?.[name]?.examples.length ? (
                  <div className="sub2">{score.checks[name].examples.join(', ')}</div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="msg ok">{t('dictionary.score.checksPassed')}</div>
      )}
      {judge?.wrong_rows.length ? (
        <table className="t" id="d-score-wrong">
          <thead>
            <tr>
              <th>{t('dictionary.changes.record')}</th>
              <th>{t('dictionary.score.reason')}</th>
              {editable ? <th /> : null}
            </tr>
          </thead>
          <tbody>
            {judge.wrong_rows.map((row) => (
              <tr key={`${row.table}.${row.column}`}>
                <td className="nm">
                  {row.column}
                  <div className="sub2">{row.table}</div>
                </td>
                <td className="desc">{row.reason}</td>
                {editable ? (
                  <td>
                    <button className="btn" type="button" onClick={() => onFix(row)}>
                      {t('dictionary.edit.open')}
                    </button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
