import {useEffect, useRef, type KeyboardEvent, type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {useIntl} from '@/contexts/IntlContext';
import {trapTab} from '@/lib/focusTrap';
import {Icon} from './Icon';

interface Props {
  title: string;
  sub?: ReactNode;
  children: ReactNode;
  foot?: ReactNode;
  wide?: boolean;
  onClose: () => void;
}

/**
 * The panel that opens from the right (search-settings Requirement 24): title, optional
 * subtitle, body, optional footer and a wide variant. It focuses its first field, keeps the
 * keyboard focus inside, closes on Esc, "Kapat (Esc)" or a click outside, and gives the focus
 * back to the control that opened it.
 */
export function Drawer({title, sub, children, foot, wide, onClose}: Props) {
  const {t} = useIntl();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const node = panel.current;
    const first =
      node?.querySelector<HTMLElement>('input, select, textarea') ?? node?.querySelector<HTMLElement>('.drawer-h .btn');
    first?.focus({preventScroll: true});
    const escape = (event: globalThis.KeyboardEvent) => {
      // Esc closes the command palette or a confirmation first when one is open over the drawer.
      if (event.key === 'Escape' && !document.querySelector('.palette, .confirm')) close.current();
    };
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('keydown', escape);
      if (opener?.isConnected) opener.focus({preventScroll: true});
    };
  }, []);

  function trap(event: KeyboardEvent<HTMLDivElement>) {
    trapTab(event, panel.current);
  }

  return createPortal(
    <div
      className={'drawer' + (wide ? ' wide' : '')}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="drawer-panel" role="dialog" aria-modal="true" aria-label={title} ref={panel} onKeyDown={trap}>
        <div className="drawer-h">
          <div className="t">
            <h2>{title}</h2>
            {sub ? <div className="sub">{sub}</div> : null}
          </div>
          <button
            className="btn ghost sm"
            type="button"
            aria-label={t('admin.drawer.close')}
            title={t('admin.drawer.close')}
            onClick={onClose}
          >
            <Icon name="x" />
          </button>
        </div>
        <div className="drawer-b">{children}</div>
        {foot ? <div className="drawer-f">{foot}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
