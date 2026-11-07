import {useIntl} from '@/contexts/IntlContext';
import {formatNumber} from '@/lib/format';

/** "‹ Önceki · 2 / 5 · Sonraki ›" under a paged list; nothing when one page holds it all. */
export function Pager({page, pageSize, total, onPage}: {page: number; pageSize: number; total: number; onPage: (page: number) => void}) {
  const {t} = useIntl();
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;
  return (
    <div className="more">
      <button className="btn sm" type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        {t('dictionary.pager.previous')}
      </button>
      <span className="note">{t('dictionary.pager.at', {page: formatNumber(page), pages: formatNumber(pages)})}</span>
      <button className="btn sm" type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        {t('dictionary.pager.next')}
      </button>
    </div>
  );
}
