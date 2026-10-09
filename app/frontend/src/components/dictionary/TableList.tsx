import {useMemo, useState, type KeyboardEvent} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import type {DictionaryTable} from '@/types/dictionary';

const STEP = 200;

/**
 * The "Tablolar" card (dictionary-management Requirement 13; admin.html PAGES.sozluk.list): the
 * group choice, the Turkish-aware search over key, group, domain and description, the first 200
 * rows and "Daha fazla (N)". A row opens the table with a click, Enter or Space.
 */
export function TableList({tables, onOpen}: {tables: readonly DictionaryTable[]; onOpen: (key: string) => void}) {
  const {t} = useIntl();
  const [query, setQuery] = useState('');
  const [group, setGroup] = useState('');
  const [shown, setShown] = useState(STEP);

  const groups = useMemo(
    () => [...new Set(tables.map((table) => table.group).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'tr')),
    [tables],
  );
  const rows = useMemo(() => {
    const needle = fold(query.trim());
    return tables.filter(
      (table) =>
        (!group || table.group === group) &&
        (!needle || fold(`${table.key} ${table.group} ${table.domain} ${table.description}`).includes(needle)),
    );
  }, [tables, query, group]);

  const keyDown = (key: string) => (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onOpen(key);
    }
  };

  return (
    <section className="card grow">
      <div className="card-h">
        <h2 id="d-title">
          {rows.length === tables.length
            ? t('dictionary.tables.title', {count: formatNumber(rows.length)})
            : t('dictionary.tables.titleFiltered', {count: formatNumber(rows.length), total: formatNumber(tables.length)})}
        </h2>
        <select
          aria-label={t('dictionary.tables.group')}
          value={group}
          onChange={(event) => {
            setGroup(event.target.value);
            setShown(STEP);
          }}
        >
          <option value="">{t('dictionary.tables.allGroups', {count: groups.length})}</option>
          {groups.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input
          type="search"
          value={query}
          placeholder={t('dictionary.tables.searchPlaceholder')}
          aria-label={t('dictionary.tables.search')}
          onChange={(event) => {
            setQuery(event.target.value);
            setShown(STEP);
          }}
        />
      </div>
      <div className="list-box" id="d-list">
        {rows.length ? (
          <>
            <table className="t">
              <thead>
                <tr>
                  <th>{t('dictionary.tables.table')}</th>
                  <th>{t('dictionary.tables.groupColumn')}</th>
                  <th className="r">{t('dictionary.tables.columns')}</th>
                  <th>{t('dictionary.tables.description')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, shown).map((table) => (
                  <tr key={table.key} className="click" tabIndex={0} onClick={() => onOpen(table.key)} onKeyDown={keyDown(table.key)}>
                    <td className="nm">
                      {table.name}
                      <div className="sub2">{table.key.split('.').slice(0, 2).join('.')}</div>
                    </td>
                    <td>{table.group || '—'}</td>
                    <td className="r">{formatNumber(table.columns)}</td>
                    <td className="desc" title={table.description || ''}>
                      <div className="clamp">{table.description || '—'}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length > shown ? (
              <div className="more">
                <button className="btn" type="button" onClick={() => setShown(shown + STEP)}>
                  {t('dictionary.tables.more', {count: formatNumber(rows.length - shown)})}
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p className="empty">{t('dictionary.tables.empty')}</p>
        )}
      </div>
    </section>
  );
}
