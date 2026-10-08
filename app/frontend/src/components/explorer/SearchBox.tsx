import {useEffect, useRef, type KeyboardEvent, type RefObject} from 'react';
import {useIntl} from '@/contexts/IntlContext';

const MAX_HEIGHT = 180;

/** Grow the question field with its text up to 180 px; a scrollbar only when it no longer fits. */
function autosize(q: HTMLTextAreaElement | null): void {
  if (!q) return;
  q.style.height = 'auto';
  q.style.height = Math.min(q.scrollHeight, MAX_HEIGHT) + 'px';
  q.style.overflowY = q.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden';
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** Enter (without Shift) or the button. */
  onSubmit: () => void;
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
}

/**
 * The question bar of the landing view (index.html #hero .searchbox): the question field that
 * grows with its text up to 180 px, the Excel list button with its drop hint, and "Ara ↵".
 */
export function SearchBox({value, onChange, onSubmit, textareaRef}: Props) {
  const {t} = useIntl();
  const own = useRef<HTMLTextAreaElement>(null);
  const field = textareaRef ?? own;

  useEffect(() => {
    autosize(field.current);
  }, [value, field]);

  useEffect(() => {
    const onResize = () => requestAnimationFrame(() => autosize(field.current));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [field]);

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="searchbox">
      <textarea
        id="q"
        ref={field}
        rows={1}
        placeholder={t('explorer.search.placeholder')}
        aria-label={t('explorer.search.label')}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={keyDown}
        autoFocus
      />
      <button
        className="attach"
        id="xl"
        type="button"
        data-tip={t('explorer.list.attachTip')}
        aria-label={t('explorer.list.attachLabel')}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3.5" y="4" width="17" height="16" rx="3" />
          <path d="M3.5 9h17M9 9v11M12 13h5.5M12 16.5h5.5" />
        </svg>
      </button>
      <div className="drop-hint" aria-hidden="true">
        <div>
          {t('explorer.list.dropTitle')}
          <small>{t('explorer.list.dropHint')}</small>
        </div>
      </div>
      <button className="primary" id="go" type="button" onClick={onSubmit}>
        {t('explorer.search.submit')} <kbd>↵</kbd>
      </button>
    </div>
  );
}
