import {useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import type {SyncSuggestion} from '@/types/dictionarySync';

interface Props {
  suggestions: SyncSuggestion[];
  busy: boolean;
  onApply: (ids: string[]) => void;
}

/**
 * The run's term and stopword suggestions (dictionary-sync Requirement 12): nothing reaches the
 * lists until the person ticks it and applies; an applied one stays on the list, marked.
 */
export function RunSuggestions({suggestions, busy, onApply}: Props) {
  const {t} = useIntl();
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());
  const chosen = suggestions.filter((item) => item.status === 'pending' && ticked.has(item.public_id)).map((item) => item.public_id);

  function toggle(id: string, on: boolean) {
    const next = new Set(ticked);
    if (on) next.add(id);
    else next.delete(id);
    setTicked(next);
  }

  if (!suggestions.length) return null;
  return (
    <section id="d-suggestions">
      <div className="card-h">
        <h2>{t('dictionary.suggestions.title')}</h2>
        <button className="btn sm primary" type="button" disabled={busy || !chosen.length} onClick={() => onApply(chosen)}>
          {t('dictionary.suggestions.apply', {count: chosen.length})}
        </button>
      </div>
      <table className="t">
        <tbody>
          {suggestions.map((item) => {
            const applied = item.status === 'applied';
            return (
              <tr key={item.public_id}>
                <td>
                  <label className="check">
                    <input
                      type="checkbox"
                      disabled={applied}
                      checked={applied || ticked.has(item.public_id)}
                      onChange={(event) => toggle(item.public_id, event.target.checked)}
                    />
                    {item.value}
                  </label>
                </td>
                <td>{t(`dictionary.suggestions.kind.${item.kind}`)}</td>
                <td>{item.equivalents.join(', ') || '—'}</td>
                <td className="desc">{item.note || '—'}</td>
                <td>{applied ? <span className="pill ok">{t('dictionary.suggestions.applied')}</span> : null}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
