import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import type {StopwordItem} from '@/types/vocabulary';

/**
 * The stopwords as group tiles (vocabulary-management Requirement 12): the groups in the order
 * they first appear, each with its count, removable word tags and a "+ kelime" box; the last
 * tile starts a new group. A word already listed (Turkish-folded) is not added.
 */
export function StopwordCard({
  stops,
  pending,
  onChange,
}: {
  stops: readonly StopwordItem[];
  pending: ReactNode;
  onChange: (items: StopwordItem[]) => void;
}) {
  const {t} = useIntl();
  const {toast} = useToast();
  const focusGroup = useRef<string | null>(null);
  const [newGroup, setNewGroup] = useState('');
  const [newWords, setNewWords] = useState('');
  const card = useRef<HTMLElement>(null);

  // After an addition the group's "+ kelime" box takes the keyboard again (admin.html addStops).
  useEffect(() => {
    const group = focusGroup.current;
    if (group === null) return;
    focusGroup.current = null;
    [...(card.current?.querySelectorAll<HTMLInputElement>('input[data-group]') ?? [])]
      .find((input) => input.dataset.group === group)
      ?.focus();
  });

  /** Add the words of a box to a group; false when none of them is new. */
  function add(group: string, text: string): boolean {
    const words = text.split(/[\s,]+/).map((word) => word.trim()).filter(Boolean);
    if (!words.length) return false;
    const have = new Set(stops.map((item) => fold(item.word)));
    const fresh = words.filter((word) => !have.has(fold(word)) && Boolean(have.add(fold(word))));
    if (!fresh.length) {
      toast(t('vocabulary.stops.already'), [words.join(', ')]);
      return false;
    }
    onChange([...stops, ...fresh.map((word) => ({word, group}))]);
    focusGroup.current = group;
    return true;
  }

  function addGroup() {
    if (!newGroup.trim() || !newWords.trim()) {
      toast(t('vocabulary.stops.groupMissing'), [], true);
      return;
    }
    if (add(newGroup.trim(), newWords)) {
      setNewGroup('');
      setNewWords('');
    }
  }

  const groups = new Map<string, [StopwordItem, number][]>();
  stops.forEach((item, at) => {
    const members = groups.get(item.group) ?? [];
    members.push([item, at]);
    groups.set(item.group, members);
  });
  return (
    <section className="w-stops" ref={card} aria-labelledby="w-stops-title">
      <div className="w-line">
        <h2 id="w-stops-title">{t('vocabulary.stops.title', {count: formatNumber(stops.length)})}</h2>
        <p className="note">{t('vocabulary.stops.intro')}</p>
      </div>
      {pending}
      <div className="sw-grid" id="w-stops">
        {[...groups].map(([group, members]) => {
          const name = group || t('vocabulary.stops.ungrouped');
          return (
            <div className="tile sw-group" key={group}>
              <div className="sw-h">
                <b>{name}</b>
                <span className="n">{formatNumber(members.length)}</span>
              </div>
              <div className="chips">
                {members.map(([item, at]) => (
                  <span className="chip" key={at}>
                    {item.word}
                    <button
                      type="button"
                      className="chip-x"
                      title={t('vocabulary.stops.remove')}
                      aria-label={t('vocabulary.stops.removeWord', {word: item.word})}
                      onClick={() => onChange(stops.filter((_, index) => index !== at))}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <input
                type="text"
                className="chip-in"
                placeholder={t('vocabulary.stops.addPlaceholder')}
                aria-label={t('vocabulary.stops.addTo', {group: name})}
                data-group={group}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter') return;
                  event.preventDefault();
                  const input = event.currentTarget;
                  if (add(group, input.value)) input.value = '';
                }}
              />
            </div>
          );
        })}
        <div className="tile sw-new">
          <div className="sw-h">
            <Icon name="plus" />
            <b>{t('vocabulary.stops.addGroup')}</b>
          </div>
          <input
            type="text"
            value={newGroup}
            placeholder={t('vocabulary.stops.newGroup')}
            aria-label={t('vocabulary.stops.newGroup')}
            onChange={(event) => setNewGroup(event.target.value)}
          />
          <input
            type="text"
            value={newWords}
            placeholder={t('vocabulary.stops.newWords')}
            aria-label={t('vocabulary.stops.newWordsLabel')}
            onChange={(event) => setNewWords(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') addGroup();
            }}
          />
          <button className="btn sm" type="button" onClick={addGroup}>
            {t('vocabulary.stops.addGroup')}
          </button>
        </div>
      </div>
    </section>
  );
}
