import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import type {StopwordItem} from '@/types/vocabulary';

/**
 * The stopwords' card (vocabulary-management Requirement 12; admin.html Words.stopCard): the
 * groups in the order they first appear, each with its count, removable word tags and a
 * "+ kelime" box; a new group at the bottom. A word already listed (Turkish-folded) is not added.
 */
export function StopwordCard({
  stops,
  actions,
  pending,
  onChange,
}: {
  stops: readonly StopwordItem[];
  actions: ReactNode;
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
  const intro = t('vocabulary.stops.intro');

  return (
    <section className="card grow w-stops" ref={card}>
      <div className="card-h">
        <h2>{t('vocabulary.stops.title', {count: formatNumber(stops.length)})}</h2>
        {actions}
      </div>
      <p className="intro" title={intro}>
        {intro}
      </p>
      {pending}
      <div className="w-scroll" id="w-stops">
        {[...groups].map(([group, members]) => {
          const name = group || t('vocabulary.stops.ungrouped');
          return (
            <div className="sw-group" key={group}>
              <div className="sw-h">
                <b>{name}</b>
                <span className="tag">{formatNumber(members.length)}</span>
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
            </div>
          );
        })}
      </div>
      <div className="sw-new">
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
          <Icon name="plus" />
          {t('vocabulary.stops.addGroup')}
        </button>
      </div>
    </section>
  );
}
