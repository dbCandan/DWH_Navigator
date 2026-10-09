import {PageHead} from '@/components/admin/PageHead';
import {Skeleton} from '@/components/admin/Skeleton';
import {SettingRow} from '@/components/settings/SettingRow';
import {SettingsCard} from '@/components/settings/SettingsCard';
import {useIntl} from '@/contexts/IntlContext';
import {useSearchState} from '@/hooks/useSearchState';
import {adminErrorText} from '@/lib/adminErrors';
import {pageOfSection, sectionFields} from '@/lib/settingsDraft';

/**
 * The "Arama ve cevap" page (search-settings Requirement 17; admin.html PAGES.arama): the plain
 * sections as cards in columns, then "Uzman ayarları" with each expert section folded. Changes go
 * into the shell's draft and apply with "Kaydet ve uygula".
 */
export default function SearchSettingsPage() {
  const {t} = useIntl();
  const {settings, settingsFailure} = useSearchState();
  const label = t('admin.page.arama.label');
  if (!settings)
    return (
      <section className="page on" id="p-arama" aria-label={label}>
        <PageHead title={label} />
        {settingsFailure ? (
          <div className="msg bad">{t('admin.pageFailed', {reason: adminErrorText(settingsFailure, t)})}</div>
        ) : (
          <Skeleton />
        )}
      </section>
    );

  const sections = settings.sections.filter((section) => pageOfSection(section.page) === 'arama');
  const plain = sections.filter((section) => !section.advanced);
  const expert = sections.filter((section) => section.advanced);
  return (
    <section className="page on" id="p-arama" aria-label={label}>
      <PageHead title={label} description={t('admin.page.arama.description')} />
      <div className="fill scroll">
        <div className="cols">
          {plain.map((section) => (
            <SettingsCard key={section.id} settings={settings} section={section} />
          ))}
          {expert.length ? (
            <div className="expert">
              <h3>{t('settings.expert.title')}</h3>
              <p className="note">{t('settings.expert.note')}</p>
              {expert.map((section) => (
                <details className="fold" key={section.id}>
                  <summary>
                    {section.title}
                    <span className="tag">{t('settings.expert.count', {count: section.fields.length})}</span>
                  </summary>
                  {section.intro ? (
                    <p className="note" title={section.intro}>
                      {section.intro}
                    </p>
                  ) : null}
                  {sectionFields(settings, section).map((field) => (
                    <SettingRow key={field.key} field={field} />
                  ))}
                </details>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
