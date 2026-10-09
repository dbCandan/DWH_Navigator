import {useState} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';

/**
 * A card's Excel round trip (vocabulary-management Requirement 13; admin.html Words.xlsxActs):
 * "Excel'den içe aktar…" opens the file picker, "Excel'e aktar" downloads the saved list.
 */
export function ListActions({onImport, onExport}: {onImport: (file: File) => void; onExport: () => void}) {
  const {t} = useIntl();
  const pick = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx';
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) onImport(file);
    };
    input.click();
  };
  return (
    <>
      <button className="btn sm" type="button" title={t('vocabulary.import.tip')} onClick={pick}>
        <Icon name="import" />
        {t('vocabulary.import.button')}
      </button>
      <button className="btn sm" type="button" title={t('vocabulary.export.tip')} onClick={onExport}>
        <Icon name="export" />
        {t('vocabulary.export.button')}
      </button>
    </>
  );
}

/**
 * A card's unsaved-changes line (vocabulary-management Requirement 13): the index is rebuilt on
 * saving; "Geri al" drops the card's edits.
 */
export function PendingBar({onRevert, onSave}: {onRevert: () => void; onSave: () => Promise<void>}) {
  const {t} = useIntl();
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try {
      await onSave();
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="msg warn wbar">
      <span>{t('vocabulary.pending.text')}</span>
      <span className="grow" />
      <button className="btn sm ghost" type="button" onClick={onRevert}>
        {t('vocabulary.pending.revert')}
      </button>
      <button className="btn sm primary" type="button" disabled={saving} onClick={() => void save()}>
        {saving ? t('admin.save.saving') : t('vocabulary.pending.save')}
      </button>
    </div>
  );
}
