import {useEffect, useRef, useState, type KeyboardEvent} from 'react';
import {fold} from '@/lib/fold';

export interface Suggestion {
  value: string;
  /** Short text at the end of the row. */
  note?: string;
}

interface Props {
  id: string;
  value: string;
  options: readonly Suggestion[];
  /** The accessible name of the list; the box takes its own from the field's label. */
  listLabel: string;
  placeholder: string;
  describedBy: string;
  mono?: boolean;
  onChange: (value: string) => void;
}

/**
 * A text box with suggestions, for the admin screen's drawers. A browser draws a native suggestion
 * list itself, outside the page's theme, so this list is the page's own. The box still takes any
 * typed text; typing narrows the list, a chosen value does not. Esc closes an open list here and
 * leaves the drawer open.
 */
export function SuggestCombobox({id, value, options, listLabel, placeholder, describedBy, mono, onChange}: Props) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState(false);
  const [active, setActive] = useState(-1);
  const list = useRef<HTMLUListElement>(null);

  const query = fold(value.trim());
  const rows = typed ? options.filter((row) => fold(row.value).includes(query)) : options;
  const shown = open && rows.length > 0;
  const optionId = (index: number) => `${id}-option-${index}`;

  useEffect(() => {
    if (!shown) return;
    list.current?.scrollIntoView?.({block: 'nearest'});
    list.current?.children[active]?.scrollIntoView?.({block: 'nearest'});
  }, [shown, active]);

  function reveal() {
    setTyped(false);
    setActive(options.findIndex((row) => row.value === value));
    setOpen(true);
  }

  function pick(row: Suggestion) {
    onChange(row.value);
    setOpen(false);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!shown) {
        reveal();
      } else {
        const step = event.key === 'ArrowDown' ? 1 : -1;
        setActive((active + step + rows.length + (active < 0 && step < 0 ? 1 : 0)) % rows.length);
      }
    } else if (event.key === 'Enter' && shown && rows[active]) {
      event.preventDefault();
      pick(rows[active]);
    } else if (event.key === 'Escape' && shown) {
      event.stopPropagation();
      setOpen(false);
    }
  }

  return (
    <div className={'combo' + (options.length ? ' has-list' : '')}>
      <input
        id={id}
        type="text"
        className={mono ? 'mono' : undefined}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={shown}
        aria-controls={id + '-list'}
        aria-activedescendant={shown && rows[active] ? optionId(active) : undefined}
        aria-describedby={describedBy}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setTyped(true);
          setActive(-1);
          setOpen(true);
        }}
        onClick={() => {
          if (!open) reveal();
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {shown && (
        <ul
          id={id + '-list'}
          className={'combo-list' + (mono ? ' mono' : '')}
          role="listbox"
          aria-label={listLabel}
          ref={list}
          // The box keeps the focus, so a click on the list or its scroll bar does not close it.
          onMouseDown={(event) => event.preventDefault()}
        >
          {rows.map((row, index) => (
            <li
              key={row.value}
              id={optionId(index)}
              className={'combo-option' + (index === active ? ' on' : '')}
              role="option"
              aria-selected={row.value === value}
              onClick={() => pick(row)}
            >
              <div className="combo-name">{row.value}</div>
              {row.note ? <small>{row.note}</small> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
