import {useEffect, useMemo, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useSettingsSave} from '@/hooks/useAdminActions';
import {useSearchState} from '@/hooks/useSearchState';
import {changedKeys, settingFields} from '@/lib/settingsDraft';

/**
 * The unsaved-changes bar (search-settings Requirement 23; admin.html #savebar): how many
 * settings are not saved and on which pages, "Geri al" and "Kaydet ve uygula". While it shows,
 * the page makes room for it (`body.unsaved`).
 */
export function SaveBar() {
  const {t} = useIntl();
  const {settings, form, revert} = useSearchState();
  const save = useSettingsSave();
  const [saving, setSaving] = useState(false);
  const keys = useMemo(() => (settings ? changedKeys(settings, form) : []), [settings, form]);
  const pages = useMemo(() => {
    if (!settings) return [];
    const fields = settingFields(settings);
    return [...new Set(keys.map((key) => fields.get(key)?.page))].map((page) => t(`admin.page.${page}.label`));
  }, [settings, keys, t]);
  const on = keys.length > 0;

  useEffect(() => {
    document.body.classList.toggle('unsaved', on);
    return () => document.body.classList.remove('unsaved');
  }, [on]);

  async function saveAll() {
    setSaving(true);
    try {
      await save();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={'savebar' + (on ? ' on' : '')} id="savebar" role="region" aria-label={t('admin.save.region')}>
      <div>
        <div className="m" id="save-msg">
          {t('admin.save.count', {count: keys.length})}
        </div>
        <div className="where" id="save-where">
          {pages.join(' · ')}
        </div>
      </div>
      <button className="btn ghost" id="revert" type="button" onClick={revert}>
        {t('admin.save.revert')}
      </button>
      <button className="btn primary" id="save" type="button" disabled={saving} onClick={() => void saveAll()}>
        {saving ? t('admin.save.saving') : t('admin.save.apply')}
      </button>
    </div>
  );
}
