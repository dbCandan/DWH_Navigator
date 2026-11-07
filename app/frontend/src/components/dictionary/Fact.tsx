import type {ReactNode} from 'react';

/** One labelled value of an `.info` row. */
export function Fact({label, value, title}: {label: string; value: ReactNode; title?: string}) {
  return (
    <div className="it" title={title ?? ''}>
      <div className="k">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}
