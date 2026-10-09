import {useEffect, useMemo, useRef, useState, type KeyboardEvent} from 'react';
import {createPortal} from 'react-dom';
import {useIntl} from '@/contexts/IntlContext';
import {filterPalette, type PaletteEntry} from '@/lib/paletteSearch';
import {Icon} from './Icon';

/**
 * The command palette (search-settings Requirement 22): Ctrl K or "Ara veya git…" opens it; the
 * typed text is folded Turkish-aware and split into words; ↑/↓ select, Enter runs, Esc or a
 * click outside closes.
 */
export function CommandPalette({entries, onClose}: {entries: readonly PaletteEntry[]; onClose: () => void}) {
  const {t} = useIntl();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const shown = useMemo(() => filterPalette(entries, query), [entries, query]);

  useEffect(() => {
    list.current?.querySelector('.pi.on')?.scrollIntoView({block: 'nearest'});
  }, [index]);

  function run(at: number) {
    const item = shown[at];
    if (!item) return;
    onClose();
    item.run();
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setIndex(Math.min(shown.length - 1, index + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setIndex(Math.max(0, index - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      run(index);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }
  }

  const nodes = [];
  let last = '';
  for (const [at, item] of shown.entries()) {
    if (item.group !== last) {
      nodes.push(
        <div className="grp" key={'g-' + item.groupId + at}>
          {item.group}
        </div>,
      );
      last = item.group;
    }
    nodes.push(
      <div
        key={at}
        className={'pi' + (at === index ? ' on' : '')}
        role="option"
        aria-selected={at === index}
        data-i={at}
        onClick={() => run(at)}
        onMouseMove={() => {
          if (at !== index) setIndex(at);
        }}
      >
        <Icon name={item.icon} />
        <div className="tx">
          <div>{item.title}</div>
          {item.subtitle ? <small>{item.subtitle}</small> : null}
        </div>
      </div>,
    );
  }

  return createPortal(
    <div
      className="palette"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette-box">
        <input
          type="text"
          placeholder={t('admin.palette.placeholder')}
          aria-label={t('admin.palette.label')}
          autoComplete="off"
          spellCheck={false}
          value={query}
          autoFocus
          onChange={(event) => {
            setQuery(event.target.value);
            setIndex(0);
          }}
          onKeyDown={keyDown}
        />
        <div className="palette-list" role="listbox" ref={list}>
          {nodes.length ? nodes : <p className="empty">{t('admin.palette.empty')}</p>}
        </div>
        <div className="palette-foot">
          <span>
            <kbd>↑↓</kbd> {t('admin.palette.select')}
          </span>
          <span>
            <kbd>Enter</kbd> {t('admin.palette.go')}
          </span>
          <span>
            <kbd>Esc</kbd> {t('admin.palette.close')}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
