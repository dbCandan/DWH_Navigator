import {useEffect, useId, useRef, useState} from 'react';
import {Link, useLocation} from 'react-router';
import {PersonIcon} from '@/components/auth/PersonIcon';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import './session.css';

/**
 * The signed-in person on the main screen's top bar: the display name, "Parolamı değiştir" and
 * "Çıkış" (user-accounts Requirement 16). Below 760 px only the icon shows, with its name.
 */
export function SessionArea() {
  const {user, logout} = useAuth();
  const {t} = useIntl();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const menu = useId();
  const area = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !area.current?.contains(event.target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        area.current?.querySelector('button')?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);

  if (!user) return null;
  const name = user.display_name || user.username;
  return (
    <div className="session" ref={area}>
      <button
        className="pill session-pill"
        type="button"
        aria-expanded={open}
        aria-controls={menu}
        aria-label={t('session.menu', {name})}
        title={name}
        onClick={() => setOpen(!open)}
      >
        <PersonIcon />
        <span className="session-name">{name}</span>
      </button>
      {open && (
        <div className="session-menu" id={menu}>
          <Link className="session-item" to="/parola" state={{from: location.pathname}}>
            {t('session.changePassword')}
          </Link>
          <button className="session-item" type="button" onClick={() => void logout()}>
            {t('session.signOut')}
          </button>
        </div>
      )}
    </div>
  );
}
