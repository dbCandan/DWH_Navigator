import type {ReactNode} from 'react';
import {Icon, type IconName} from './Icon';

export interface HeroStat {
  label: string;
  value: ReactNode;
  /** A short line under the value. */
  note?: ReactNode;
  /** Colours the value: a state that is fine, needs a look, or is broken. */
  tone?: 'ok' | 'warn' | 'bad';
}

/**
 * A redesigned page's head: the page's icon, title and one-line purpose, its actions, and a strip
 * of the few numbers that tell the page's state before anything is read below.
 */
export function PageHero({
  icon,
  title,
  description,
  actions,
  stats,
}: {
  icon: IconName;
  title: string;
  description?: string;
  actions?: ReactNode;
  stats?: readonly HeroStat[];
}) {
  return (
    <header className="hero-band">
      <div className="hb-top">
        <div className="hb-icon" aria-hidden="true">
          <Icon name={icon} />
        </div>
        <div className="hb-t">
          <h1>{title}</h1>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="hb-acts">{actions}</div> : null}
      </div>
      {stats?.length ? (
        <dl className="hb-stats">
          {stats.map((stat) => (
            <div className={'st' + (stat.tone ? ' ' + stat.tone : '')} key={stat.label}>
              <dt>{stat.label}</dt>
              <dd>{stat.value}</dd>
              {stat.note ? <small>{stat.note}</small> : null}
            </div>
          ))}
        </dl>
      ) : null}
    </header>
  );
}
