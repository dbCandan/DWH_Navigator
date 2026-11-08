import {useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {
  COLUMN_EDIT_FIELDS,
  OBJECT_EDIT_FIELDS,
  type SyncEditField,
  type SyncRecordEdit,
} from '@/types/dictionarySync';

const ROLES = ['Anahtar', 'Kod', 'Ad', 'Zaman', 'Ölçü', 'Bayrak', 'Metin'] as const;
const SUMMARY_MAX = 70;

interface Props {
  tableKey: string;
  columnName: string;
  /** The field and value to start from, e.g. the change line the admin clicked. */
  field?: SyncEditField;
  value?: string;
  busy: boolean;
  onSave: (edit: SyncRecordEdit) => void;
  onCancel: () => void;
}

/**
 * An admin's text for one field of the version waiting for approval. What is saved here gets the
 * admin origin: no later update, model or rule rewrites it.
 */
export function RecordEditor({tableKey, columnName, field, value, busy, onSave, onCancel}: Props) {
  const {t} = useIntl();
  const fields: readonly SyncEditField[] = columnName ? COLUMN_EDIT_FIELDS : OBJECT_EDIT_FIELDS;
  const start = field && fields.includes(field) ? field : fields[0];
  const [chosen, setChosen] = useState<SyncEditField>(start);
  // A role is one of the fixed names: an empty or unknown one starts from the first.
  const [text, setText] = useState(start === 'Role' && !ROLES.includes(value as (typeof ROLES)[number]) ? ROLES[0] : (value ?? ''));
  const tooLong = chosen === 'Summary' && text.trim().length > SUMMARY_MAX;
  const empty = (chosen === 'ColumnDescription' || chosen === 'ObjectDescription') && !text.trim();

  return (
    <form
      className="record-editor"
      aria-label={t('dictionary.edit.title')}
      onSubmit={(event) => {
        event.preventDefault();
        if (!tooLong && !empty) onSave({table_key: tableKey, column_name: columnName, field: chosen, value: text.trim()});
      }}
    >
      <div className="sub2">
        {columnName ? `${tableKey}.${columnName}` : tableKey}
      </div>
      <label>
        {t('dictionary.edit.field')}
        <select
          value={chosen}
          onChange={(event) => {
            const next = event.target.value as SyncEditField;
            setChosen(next);
            if (next === 'Role' && !ROLES.includes(text as (typeof ROLES)[number])) setText(ROLES[0]);
          }}
        >
          {fields.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      {chosen === 'Role' ? (
        <label>
          {t('dictionary.edit.value')}
          <select value={text} onChange={(event) => setText(event.target.value)}>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label>
          {t('dictionary.edit.value')}
          <textarea rows={chosen === 'Summary' ? 2 : 5} value={text} onChange={(event) => setText(event.target.value)} />
        </label>
      )}
      {tooLong ? <div className="msg bad">{t('dictionary.edit.summaryTooLong', {max: String(SUMMARY_MAX)})}</div> : null}
      {empty ? <div className="msg bad">{t('dictionary.edit.empty')}</div> : null}
      <p className="sub2">{t('dictionary.edit.notice')}</p>
      <div className="row-actions">
        <button className="btn" type="button" disabled={busy} onClick={onCancel}>
          {t('dictionary.edit.cancel')}
        </button>
        <button className="btn primary" type="submit" disabled={busy || tooLong || empty}>
          {t('dictionary.edit.save')}
        </button>
      </div>
    </form>
  );
}
