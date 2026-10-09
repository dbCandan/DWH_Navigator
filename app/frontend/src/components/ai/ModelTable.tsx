import type {ReactNode} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {formatNumber} from '@/lib/format';
import type {LlmModelRow} from '@/types/llm';

/**
 * One server's models (admin.html AI.table): Model, Bağlam, Durum ("Kullanımda", "Yüklü",
 * "Yüklü değil") and the row's action, if any.
 */
export function ModelTable({rows, action}: {rows: readonly LlmModelRow[]; action?: (row: LlmModelRow) => ReactNode}) {
  const {t} = useIntl();
  if (!rows.length) return <p className="note">{t('ai.models.none')}</p>;
  return (
    <div className="scroll">
      <table className="t">
        <thead>
          <tr>
            <th>{t('ai.models.model')}</th>
            <th className="r">{t('ai.models.context')}</th>
            <th>{t('ai.models.status')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="nm">{row.id}</td>
              <td className="r">{row.context ? formatNumber(row.context) : t('ai.models.noContext')}</td>
              <td>
                {row.in_use ? (
                  <span className="tag on">{t('ai.models.inUse')}</span>
                ) : row.loaded === true ? (
                  <span className="tag">{t('ai.models.loaded')}</span>
                ) : row.loaded === false ? (
                  <span className="tag">{t('ai.models.notLoaded')}</span>
                ) : null}
              </td>
              <td className="r">{action ? action(row) : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
