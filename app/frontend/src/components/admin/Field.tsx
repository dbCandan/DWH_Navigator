import type {ReactNode} from 'react';

/**
 * A labelled form field (admin.html .fld): the label, the control, an optional hint that the
 * control names in `aria-describedby` (`<id>-hint`), so the hint is not part of its name.
 */
export function Field({id, label, hint, children}: {id: string; label: string; hint?: string; children: ReactNode}) {
  return (
    <div className="fld">
      <span>
        <label htmlFor={id}>{label}</label>
      </span>
      {children}
      {hint ? <small id={id + '-hint'}>{hint}</small> : null}
    </div>
  );
}
