import {useEffect, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {formatNumber} from '@/lib/format';
import {DictionarySyncService} from '@/services/dictionarySync';
import {SYNC_CHANGE_KINDS, type SyncChange, type SyncChangeKind, type SyncPage} from '@/types/dictionarySync';
import {Pager} from './Pager';

const PAGE_SIZE = 50;
const SEARCH_DELAY_MS = 300;

/** A long value keeps its row short; the whole text is in the tooltip. */
function Value({text}: {text: string}) {
  return (
    <td className="desc" title={text}>
      <div className="clamp">{text || '—'}</div>
    </td>
  );
}

/**
 * The report's change lines (dictionary-sync Requirement 9; plan.md Yazım düzeltme): filtered by
 * kind and text and paged on the server. The old and the new value sit side by side, which for a
 * corrected name are the source's and the catalog's spelling.
 */
export function RunChanges({runId, onEdit}: {runId: string; onEdit?: (change: SyncChange) => void}) {
  const {t} = useIntl();
  const {reportUnreachable} = useToast();
  const [kind, setKind] = useState<SyncChangeKind | ''>('');
  const [typed, setTyped] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [answer, setAnswer] = useState<SyncPage<SyncChange> | null>(null);
  const [failure, setFailure] = useState('');

  useEffect(() => {
    const next = typed.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [typed, search]);

  useEffect(() => {
    let live = true;
    DictionarySyncService.changes(runId, {kind, search, page, pageSize: PAGE_SIZE}).then(
      (next) => {
        if (!live) return;
        setAnswer(next);
        setFailure('');
      },
      (error: unknown) => {
        reportUnreachable(error);
        if (live) setFailure(adminErrorText(error, t));
      },
    );
    return () => {
      live = false;
    };
  }, [runId, kind, search, page, t, reportUnreachable]);

  return (
    <section id="d-changes">
      <div className="card-h">
        <h2>{t('dictionary.changes.title', {count: formatNumber(answer?.total ?? 0)})}</h2>
        <select
          aria-label={t('dictionary.changes.kind')}
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as SyncChangeKind | '');
            setPage(1);
          }}
        >
          <option value="">{t('dictionary.changes.allKinds')}</option>
          {SYNC_CHANGE_KINDS.map((name) => (
            <option key={name} value={name}>
              {t(`dictionary.changes.kind.${name}`)}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={typed}
          placeholder={t('dictionary.changes.searchPlaceholder')}
          aria-label={t('dictionary.changes.search')}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>
      {failure ? <div className="msg bad">{failure}</div> : null}
      {answer?.items.length ? (
        <>
          <table className="t">
            <thead>
              <tr>
                <th>{t('dictionary.changes.kindColumn')}</th>
                <th>{t('dictionary.changes.record')}</th>
                <th>{t('dictionary.changes.field')}</th>
                <th>{t('dictionary.changes.old')}</th>
                <th>{t('dictionary.changes.new')}</th>
                <th>{t('dictionary.changes.origin')}</th>
                {onEdit ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {answer.items.map((change, at) => (
                <tr key={at}>
                  <td>{t(`dictionary.changes.kind.${change.kind}`)}</td>
                  <td className="nm">
                    {change.column_name || change.table_key}
                    {change.column_name ? <div className="sub2">{change.table_key}</div> : null}
                  </td>
                  <td>{change.field || '—'}</td>
                  <Value text={change.old_value} />
                  <Value text={change.new_value} />
                  <td>{change.origin ? t(`dictionary.changes.origin.${change.origin}`) : '—'}</td>
                  {onEdit ? (
                    <td>
                      {change.table_key && !change.kind.endsWith('_removed') ? (
                        <button className="btn" type="button" onClick={() => onEdit(change)}>
                          {t('dictionary.edit.open')}
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={answer.page} pageSize={PAGE_SIZE} total={answer.total} onPage={setPage} />
        </>
      ) : answer && !failure ? (
        <p className="empty">{t('dictionary.changes.empty')}</p>
      ) : null}
    </section>
  );
}
