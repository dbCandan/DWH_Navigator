import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {versionDigits} from '@/lib/adminStatus';
import {formatDateTime, formatNumber} from '@/lib/format';
import type {DictionaryVersion} from '@/types/dictionarySync';

const PILL: Record<DictionaryVersion['status'], string> = {active: 'pill ok', previous: 'pill', pending: 'pill warn'};

interface Props {
  versions: DictionaryVersion[] | null;
  /** While a run goes on the server refuses a return (Requirement 10). */
  busy: boolean;
  onRestore: (version: DictionaryVersion) => void;
  onReport: (runId: string) => void;
}

/** The kept versions (dictionary-sync Requirement 10): "Bu sürüme dön" only where it is possible. */
export function VersionList({versions, busy, onRestore, onReport}: Props) {
  const {t} = useIntl();
  return (
    <section className="card" id="d-versions">
      <h2>{t('dictionary.versions.title')}</h2>
      <p className="intro">{t('dictionary.versions.intro')}</p>
      {versions === null ? (
        <Skeleton />
      ) : versions.length ? (
        <table className="t">
          <thead>
            <tr>
              <th>{t('dictionary.versions.version')}</th>
              <th>{t('dictionary.versions.status')}</th>
              <th>{t('dictionary.versions.date')}</th>
              <th>{t('dictionary.versions.by')}</th>
              <th className="r">{t('dictionary.versions.tables')}</th>
              <th className="r">{t('dictionary.versions.columns')}</th>
              <th>{t('dictionary.versions.expires')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {versions.map((version) => {
              const {run_public_id: runId} = version;
              return (
                <tr key={version.public_id}>
                  <td className="mono" title={version.version}>
                    {versionDigits(version.version)}
                  </td>
                  <td>
                    <span className={PILL[version.status]}>{t(`dictionary.versions.status.${version.status}`)}</span>
                  </td>
                  <td>{formatDateTime(version.imported_at)}</td>
                  <td>{version.imported_by?.display_name ?? '—'}</td>
                  <td className="r">{formatNumber(version.object_count)}</td>
                  <td className="r">{formatNumber(version.column_count)}</td>
                  <td>{version.expires_at ? formatDateTime(version.expires_at) : '—'}</td>
                  <td className="r">
                    {runId ? (
                      <button className="btn sm ghost" type="button" onClick={() => onReport(runId)}>
                        {t('dictionary.versions.report')}
                      </button>
                    ) : null}
                    {version.can_restore ? (
                      <button className="btn sm" type="button" disabled={busy} onClick={() => onRestore(version)}>
                        {t('dictionary.versions.restore')}
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="empty">{t('dictionary.versions.empty')}</p>
      )}
    </section>
  );
}
