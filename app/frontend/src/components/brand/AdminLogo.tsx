import {useId} from 'react';
import './brand.css';

/** The admin screen's mark (admin.html .brand): the compass needle in the app gradient. */
export function AdminLogo() {
  const gradient = useId();
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop className="logo-stop-start" offset="0" />
          <stop className="logo-stop-mid" offset=".55" />
          <stop className="logo-stop-end" offset="1" />
        </linearGradient>
      </defs>
      <circle className="logo-disc" cx="16" cy="16" r="14" stroke={`url(#${gradient})`} strokeWidth="1.5" />
      <path d="M16 5l4 11-4 11-4-11z" fill={`url(#${gradient})`} />
    </svg>
  );
}
