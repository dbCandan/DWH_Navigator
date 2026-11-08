import {PageHero} from '@/components/admin/PageHero';
import {Skeleton} from '@/components/admin/Skeleton';
import {SettingRow} from '@/components/settings/SettingRow';
import {SettingsCard} from '@/components/settings/SettingsCard';
import {useIntl} from '@/contexts/IntlContext';
import {useSearchState} from '@/hooks/useSearchState';
import {adminErrorText} from '@/lib/adminErrors';
import {pageOfSection, sameValue, sectionFields} from '@/lib/settingsDraft';
import type {SearchSettingSection} from '@/types/search';
import '@/components/settings/settings.css';

/** Bring a section into view; an expert section is unfolded first. */
function goTo(section: SearchSettingSection) {
  const node = document.getElementById('sec-' + section.id);
  if (!node) return;
  if (node instanceof HTMLDetailsElement) node.open = true;
  node.scrollIntoView({behavior: 'smooth', block: 'start'});
}

/**
 * The "Arama ve cevap" page (search-settings Requirement 17): the hero counts the settings, those
 * off their default and those not saved yet; the left rail lists the sections (a dot where a value
 * waits to be saved) and jumps to them; the plain sections are panels, the expert ones folded
 * panels under their own heading. Changes go into the shell's draft and apply with
 * "Kaydet ve uygula".
 */
export default function SearchSettingsPage() {
  const {t} = useIntl();
  const {settings, settingsFailure, form} = useSearchState();
  const label = t('admin.page.arama.label');
  if (!settings)
    return (
      <section className="page on" id="p-arama" aria-label={label}>
        <PageHero icon="sliders" title={label} />
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
  const keys = sections.flatMap((section) => section.fields.map((field) => field.key));
  const unsaved = (section: SearchSettingSection) =>
    section.fields.filter((field) => !sameValue(form[field.key], settings.values[field.key])).length;
  const offDefault = keys.filter((key) => !sameValue(form[key], settings.defaults[key])).length;
  const waiting = sections.reduce((sum, section) => sum + unsaved(section), 0);

  const navItem = (section: SearchSettingSection) => {
    const count = unsaved(section);
    return (
      <li key={section.id}>
        <button type="button" onClick={() => goTo(section)}>
          <span className="t">{section.title}</span>
          {count ? <span className="dot" title={t('settings.nav.unsaved', {count})} /> : null}
          <span className="n">{section.fields.length}</span>
        </button>
      </li>
    );
  };

  return (
    <section className="page on" id="p-arama" aria-label={label}>
      <PageHero
        icon="sliders"
        title={label}
        description={t('admin.page.arama.description')}
        stats={[
          {label: t('settings.stat.total'), value: keys.length, note: t('settings.stat.sections', {count: sections.length})},
          {
            label: t('settings.stat.offDefault'),
            value: offDefault,
            note: t('settings.stat.offDefaultNote'),
            tone: offDefault ? 'warn' : 'ok',
          },
          {
            label: t('settings.stat.unsaved'),
            value: waiting,
            note: t(waiting ? 'settings.stat.unsavedNote' : 'settings.stat.allSaved'),
            tone: waiting ? 'warn' : 'ok',
          },
        ]}
      />
      <div className="fill set-layout">
        <nav className="set-nav" aria-label={t('settings.nav.label')}>
          <div className="grp">{t('settings.nav.basic')}</div>
          <ul>{plain.map(navItem)}</ul>
          {expert.length ? (
            <>
              <div className="grp">{t('settings.expert.title')}</div>
              <ul>{expert.map(navItem)}</ul>
            </>
          ) : null}
        </nav>
        <div className="set-main scroll">
          <div className="set-cols">
            {plain.map((section) => (
              <SettingsCard key={section.id} settings={settings} section={section} />
            ))}
          </div>
          {expert.length ? (
            <div className="expert">
              <div className="expert-h">
                <h3>{t('settings.expert.title')}</h3>
                <p className="note">{t('settings.expert.note')}</p>
              </div>
              {expert.map((section) => (
                <details className="panel set-panel fold-panel" key={section.id} id={'sec-' + section.id}>
                  <summary>
                    <span className="t">{section.title}</span>
                    <span className="tag">{t('settings.expert.count', {count: section.fields.length})}</span>
                    {section.intro ? <span className="sub">{section.intro}</span> : null}
                  </summary>
                  <div className="panel-b">
                    {sectionFields(settings, section).map((field) => (
                      <SettingRow key={field.key} field={field} />
                    ))}
                  </div>
                </details>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
