import {useMemo, useState, type ReactNode} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import type {TermItem} from '@/types/vocabulary';

/** How many equivalents a tile shows before "+n". */
const SHOWN = 8;

/**
 * The term dictionary as tiles (vocabulary-management Requirement 10): the Turkish-aware search
 * over term, equivalents, domain and note, the domains as filter chips with their counts, the
 * unsaved-changes line, then one tile per term. A tile opens the term's drawer; the dashed tile
 * adds a term.
 */
export function TermCard({
  terms,
  pending,
  onEdit,
}: {
  terms: readonly TermItem[];
  pending: ReactNode;
  onEdit: (at: number) => void;
}) {
  const {t} = useIntl();
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState<string | null>(null);
  const domains = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of terms) counts.set(item.domain, (counts.get(item.domain) ?? 0) + 1);
    return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'tr'));
  }, [terms]);
  const rows = useMemo(() => {
    const needle = fold(query.trim());
    return terms
      .map((item, at) => [item, at] as const)
      .filter(([item]) => domain === null || item.domain === domain)
      .filter(([item]) => !needle || fold([item.term, ...item.equivalents, item.domain, item.note].join(' ')).includes(needle));
  }, [terms, query, domain]);
  const filtered = rows.length !== terms.length;

  return (
    <section className="w-terms" aria-labelledby="w-title">
      <div className="w-tools">
        <input
          type="search"
          value={query}
          placeholder={t('vocabulary.terms.searchPlaceholder')}
          aria-label={t('vocabulary.terms.search')}
          onChange={(event) => setQuery(event.target.value)}
        />
        {domains.length > 1 ? (
          <div className="fchips" role="group" aria-label={t('vocabulary.terms.domainFilter')}>
            <button className="fchip" type="button" aria-pressed={domain === null} onClick={() => setDomain(null)}>
              {t('vocabulary.terms.allDomains')}
              <i>{formatNumber(terms.length)}</i>
            </button>
            {domains.map(([name, count]) => (
              <button className="fchip" type="button" key={name} aria-pressed={domain === name} onClick={() => setDomain(domain === name ? null : name)}>
                {name || t('vocabulary.terms.noDomain')}
                <i>{formatNumber(count)}</i>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="w-line">
        <h2 id="w-title">
          {filtered
            ? t('vocabulary.terms.titleFiltered', {count: formatNumber(rows.length), total: formatNumber(terms.length)})
            : t('vocabulary.terms.title', {count: formatNumber(rows.length)})}
        </h2>
        <p className="note">{t('vocabulary.terms.intro')}</p>
      </div>
      {pending}
      <div className="term-grid" id="w-terms">
        {!filtered ? (
          <button className="tile add" type="button" onClick={() => onEdit(-1)}>
            <Icon name="plus" />
            {t('vocabulary.terms.new')}
          </button>
        ) : null}
        {rows.map(([item, at]) => (
          <button className="tile term" type="button" key={at} onClick={() => onEdit(at)} aria-label={t('vocabulary.terms.open', {term: item.term})}>
            <span className="th">
              <b className="nm">{item.term}</b>
              {item.domain ? <span className="dom">{item.domain}</span> : null}
            </span>
            <span className="chips">
              {item.equivalents.slice(0, SHOWN).map((word, index) => (
                <span className="tag" key={index}>
                  {word}
                </span>
              ))}
              {item.equivalents.length > SHOWN ? (
                <span className="tag more">+{formatNumber(item.equivalents.length - SHOWN)}</span>
              ) : null}
            </span>
            {item.note ? <span className="tnote">{item.note}</span> : null}
          </button>
        ))}
        {!rows.length ? <p className="empty">{terms.length ? t('vocabulary.terms.noMatch') : t('vocabulary.terms.empty')}</p> : null}
      </div>
    </section>
  );
}
