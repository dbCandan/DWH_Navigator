import type {ReactNode} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {sectionFields} from '@/lib/settingsDraft';
import type {SearchSettings, SearchSettingSection} from '@/types/search';
import {SettingRow} from './SettingRow';

/**
 * One settings section as a card (admin.html Settings.card): its title and one-line intro, the
 * plain fields, then its expert fields folded under "Uzman ayarları (N)".
 */
export function SettingsCard({settings, section, children}: {settings: SearchSettings; section: SearchSettingSection; children?: ReactNode}) {
  const {t} = useIntl();
  const fields = sectionFields(settings, section);
  const basic = fields.filter((field) => !field.advanced);
  const expert = fields.filter((field) => field.advanced);
  return (
    <section className="card" id={'sec-' + section.id}>
      <h2>{section.title}</h2>
      {section.intro ? (
        <p className="intro" title={section.intro}>
          {section.intro}
        </p>
      ) : null}
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
    </section>
  );
}
