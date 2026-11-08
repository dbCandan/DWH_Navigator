import type {ReactNode} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {sectionFields} from '@/lib/settingsDraft';
import type {SearchSettings, SearchSettingSection} from '@/types/search';
import {SettingRow} from './SettingRow';
import './settings.css';

/**
 * One settings section as a panel: its title and intro in the head, the plain fields, then the
 * section's rarely changed fields folded under "Gelişmiş ayarlar (N)", then what the page adds.
 */
export function SettingsCard({
  settings,
  section,
  children,
  aside,
}: {
  settings: SearchSettings;
  section: SearchSettingSection;
  children?: ReactNode;
  /** Shown at the right of the panel's head (a count, a state). */
  aside?: ReactNode;
}) {
  const {t} = useIntl();
  const fields = sectionFields(settings, section);
  const basic = fields.filter((field) => !field.advanced);
  const expert = fields.filter((field) => field.advanced);
  return (
    <section className="panel set-panel" id={'sec-' + section.id}>
      <div className="panel-h">
        <h2>{section.title}</h2>
        {aside}
        {section.intro ? <p className="sub">{section.intro}</p> : null}
      </div>
      <div className="panel-b">
        {basic.map((field) => (
          <SettingRow key={field.key} field={field} />
        ))}
        {expert.length ? (
          <details className="fold">
            <summary>{t('settings.expertFold', {count: expert.length})}</summary>
            {expert.map((field) => (
              <SettingRow key={field.key} field={field} />
            ))}
          </details>
        ) : null}
        {children}
      </div>
    </section>
  );
}
