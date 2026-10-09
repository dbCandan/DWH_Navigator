import type {ReactNode} from 'react';

/** A page's heading (admin.html pageHead): title, one-line description (whole text in the tooltip), actions. */
export function PageHead({title, description, actions}: {title: string; description?: string; actions?: ReactNode}) {
  return (
    <div className="ph">
      <div className="t">
        <h1>{title}</h1>
        {description ? <p title={description}>{description}</p> : null}
      </div>
      {actions ? <div className="acts">{actions}</div> : null}
    </div>
  );
}
