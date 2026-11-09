import {useEffect, useRef, type KeyboardEvent, type RefObject} from 'react';
import {useIntl} from '@/contexts/IntlContext';

const MAX_HEIGHT = 180;

/** Grow the question field with its text up to 180 px; a scrollbar only when it no longer fits. */
function autosize(q: HTMLTextAreaElement | null, docked: boolean): void {
  if (!q) return;
  if (docked) {
    // One line in the heading: the stylesheet gives the height.
    q.style.height = '';
    q.style.overflowY = '';
    return;
  }
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
  /** The bar sits in the top line as the page's heading (after the first question). */
  docked?: boolean;
  /** An analysis runs: the button says "Durdur" and stops it. */
  busy?: boolean;
  onStop?: () => void;
  /** The asked question, as the field's tooltip in the heading. */
  title?: string;
  /** The Excel list button: pick a list file (list-search Requirement 17). */
  onAttach?: () => void;
  /** The welcome tour's copy of the bar: it leaves the page's ids and the focus to the real one. */
  sample?: boolean;
}

/**
 * The question bar (index.html .searchbox): the question field that grows with its text up to
 * 180 px on the landing view and stays one line in the heading, the Excel list button with its
 * drop hint, and "Ara ↵", which turns into "Durdur" while an analysis runs (question-analysis
 * Requirement 19).
 */
export function SearchBox({
  value,
  onChange,
  onSubmit,
  textareaRef,
  docked = false,
  busy = false,
  onStop,
  title,
  onAttach,
  sample = false,
}: Props) {
  const {t} = useIntl();
  const own = useRef<HTMLTextAreaElement>(null);
  const field = textareaRef ?? own;

  useEffect(() => {
    autosize(field.current, docked);
  }, [value, field, docked]);

  useEffect(() => {
    const onResize = () => requestAnimationFrame(() => autosize(field.current, docked));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [field, docked]);

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="searchbox">
      <textarea
        id={sample ? undefined : 'q'}
        ref={field}
        rows={1}
        placeholder={t('explorer.search.placeholder')}
        aria-label={t('explorer.search.label')}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={keyDown}
        wrap={docked ? 'off' : undefined}
        title={title}
        autoFocus={!docked && !sample}
      />
      <button
        className="attach"
        id={sample ? undefined : 'xl'}
        type="button"
        data-tip={t('explorer.list.attachTip')}
        aria-label={t('explorer.list.attachLabel')}
        onClick={onAttach}
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
      <button
        className={'primary' + (busy ? ' busy' : '')}
        id={sample ? undefined : 'go'}
        type="button"
        title={busy ? t('explorer.search.stopTip') : undefined}
        aria-label={busy ? t('explorer.search.stop') : undefined}
        onClick={busy ? onStop : onSubmit}
      >
        {t('explorer.search.submit')} <kbd>↵</kbd>
      </button>
    </div>
  );
}
