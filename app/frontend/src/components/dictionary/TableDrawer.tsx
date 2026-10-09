import {useEffect, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {adminErrorText} from '@/lib/adminErrors';
import {formatNumber} from '@/lib/format';
import {DictionaryService} from '@/services/dictionary';
import type {DictionaryTableRecords} from '@/types/dictionary';

type Loaded = {key: string; records: DictionaryTableRecords} | {key: string; failure: unknown};

/**
 * A table's records as imported (dictionary-management Requirement 13; admin.html
 * PAGES.sozluk.openTable): its description, the Objeler fields and the Kolonlar rows.
 */
export function TableDrawer({tableKey, onClose}: {tableKey: string; onClose: () => void}) {
  const {t} = useIntl();
  const {reportUnreachable} = useToast();
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let live = true;
    DictionaryService.table(tableKey).then(
      (records) => live && setLoaded({key: tableKey, records}),
      (failure: unknown) => {
        reportUnreachable(failure);
        if (live) setLoaded({key: tableKey, failure});
      },
    );
    return () => {
      live = false;
    };
  }, [tableKey, reportUnreachable]);

  const current = loaded?.key === tableKey ? loaded : null;
  let body;
  if (current === null) body = <Skeleton />;
  else if ('failure' in current) body = <div className="msg bad">{adminErrorText(current.failure, t)}</div>;
  else {
    const object = current.records.object ?? {};
    const columns = current.records.columns;
    const facts: [string, string | undefined][] = [
      [t('dictionary.table.group'), object.DatasetGroup],
      [t('dictionary.table.domain'), object.BusinessDomain],
      [t('dictionary.table.grain'), object.Grain],
      [t('dictionary.table.keys'), object.KeyColumns],
      [t('dictionary.table.time'), object.TimeColumns],
    ];
    body = (
      <>
        {object.ObjectDescription ? <p>{object.ObjectDescription}</p> : <p className="muted">{t('dictionary.table.noDescription')}</p>}
        <dl className="kv">
          {facts.map(([label, value]) =>
            value ? [<dt key={label + '-t'}>{label}</dt>, <dd key={label + '-d'}>{value}</dd>] : null,
          )}
        </dl>
        <div className="sec-t">{t('dictionary.table.columns', {count: formatNumber(columns.length)})}</div>
        <table className="t">
          <thead>
            <tr>
              <th>{t('dictionary.table.column')}</th>
              <th>{t('dictionary.table.role')}</th>
              <th>{t('dictionary.table.description')}</th>
              <th>{t('dictionary.table.synonyms')}</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column, at) => (
              <tr key={at}>
                <td className="nm">
                  {column.ColumnName || '—'}
                  {column.Summary ? <div className="sub2">{column.Summary}</div> : null}
                </td>
                <td>{column.Role ? <span className="role">{column.Role}</span> : '—'}</td>
                <td className="desc">{column.ColumnDescription || '—'}</td>
                <td className="desc">{column.Synonyms || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </>
    );
  }
  return (
    <Drawer title={tableKey.split('.').pop() ?? tableKey} sub={tableKey} wide onClose={onClose}>
      {body}
    </Drawer>
  );
}
