import {useMemo, useState, type KeyboardEvent, type ReactNode} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import type {TermItem} from '@/types/vocabulary';

/**
 * The term dictionary's card (vocabulary-management Requirement 10; admin.html Words.termCard):
 * the count, the Turkish-aware search over term, equivalents, domain and note, the Excel actions,
 * "Yeni terim", the unsaved-changes line and the table. A row opens the drawer with a click,
 * Enter or Space.
 */
export function TermCard({
  terms,
  actions,
  pending,
  onEdit,
}: {
  terms: readonly TermItem[];
  actions: ReactNode;
  pending: ReactNode;
  onEdit: (at: number) => void;
}) {
  const {t} = useIntl();
  const [query, setQuery] = useState('');
  const rows = useMemo(() => {
    const needle = fold(query.trim());
    return terms
      .map((item, at) => [item, at] as const)
      .filter(([item]) => !needle || fold([item.term, ...item.equivalents, item.domain, item.note].join(' ')).includes(needle));
  }, [terms, query]);
  const keyDown = (at: number) => (event: KeyboardEvent<HTMLTableRowElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onEdit(at);
    }
  };
  const intro = t('vocabulary.terms.intro');
  return (
    <section className="card grow w-terms">
      <div className="card-h">
        <h2 id="w-title">
          {rows.length === terms.length
            ? t('vocabulary.terms.title', {count: formatNumber(rows.length)})
            : t('vocabulary.terms.titleFiltered', {count: formatNumber(rows.length), total: formatNumber(terms.length)})}
        </h2>
        <input
          type="search"
          value={query}
          placeholder={t('vocabulary.terms.searchPlaceholder')}
          aria-label={t('vocabulary.terms.search')}
          onChange={(event) => setQuery(event.target.value)}
        />
        {actions}
        <button className="btn sm primary" type="button" onClick={() => onEdit(-1)}>
          <Icon name="plus" />
          {t('vocabulary.terms.new')}
        </button>
      </div>
      <p className="intro" title={intro}>
        {intro}
      </p>
      {pending}
      <div className="list-box" id="w-terms">
        {rows.length ? (
          <table className="t">
            <thead>
              <tr>
                <th>{t('vocabulary.terms.term')}</th>
                <th>{t('vocabulary.terms.equivalents')}</th>
                <th>{t('vocabulary.terms.domain')}</th>
                <th>{t('vocabulary.terms.note')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([item, at]) => (
                <tr key={at} className="click" tabIndex={0} onClick={() => onEdit(at)} onKeyDown={keyDown(at)}>
                  <td className="nm">{item.term}</td>
                  <td>
                    <div className="chips">
                      {item.equivalents.map((word, index) => (
                        <span className="tag" key={index}>
                          {word}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>{item.domain || '—'}</td>
                  <td className="desc" title={item.note}>
                    <div className="clamp">{item.note || '—'}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">{terms.length ? t('vocabulary.terms.noMatch') : t('vocabulary.terms.empty')}</p>
        )}
      </div>
    </section>
  );
}
