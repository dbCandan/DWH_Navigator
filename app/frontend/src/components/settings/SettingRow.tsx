import {useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useSearchState} from '@/hooks/useSearchState';
import {sameValue, showValue, type SettingField} from '@/lib/settingsDraft';
import type {SettingValue} from '@/types/search';

/**
 * The number box beside a slider (admin.html Settings.control): it shows the value with the
 * step's decimals, follows the slider and "↺", and takes a typed number when it parses.
 */
function NumberBox({field, value, onChange}: {field: SettingField; value: number; onChange: (value: number) => void}) {
  const step = field.step || (field.type === 'int' ? 1 : 0.05);
  const parse = (text: string) => (field.type === 'int' ? parseInt(text, 10) : parseFloat(text));
  const [text, setText] = useState(() => showValue(field, value, ''));
  const [shown, setShown] = useState(value);
  if (!sameValue(shown, value)) {
    setShown(value);
    if (!sameValue(parse(text), value)) setText(showValue(field, value, ''));
  }
  return (
    <input
      type="number"
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      step={step}
      value={text}
      aria-label={field.label}
      onChange={(event) => {
        setText(event.target.value);
        const parsed = parse(event.target.value);
        if (!Number.isNaN(parsed)) onChange(parsed);
      }}
    />
  );
}

function Control({field, value, onChange}: {field: SettingField; value: SettingValue; onChange: (value: SettingValue) => void}) {
  const {t} = useIntl();
  if (field.type === 'bool')
    return (
      <label className="switch">
        <input type="checkbox" aria-label={field.label} checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        <span />
      </label>
    );
  const step = field.step || (field.type === 'int' ? 1 : 0.05);
  const number = Number(value);
  const parse = (text: string) => (field.type === 'int' ? parseInt(text, 10) : parseFloat(text));
  const range = (
    <input
      type="range"
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      step={step}
      value={number}
      aria-label={field.label}
      onChange={(event) => onChange(parse(event.target.value))}
    />
  );
  if (field.format === 'pct')
    return (
      <>
        {range}
        <span className="readout">{showValue(field, number, t('settings.empty'))}</span>
      </>
    );
  return (
    <>
      {range}
      <NumberBox field={field} value={number} onChange={onChange} />
    </>
  );
}

/**
 * One setting (search-settings Requirement 18; admin.html Settings.row): the label (the key in
 * its tooltip), the `indeks` tag, the one-line help, the control and "↺". A changed row and a row
 * off its default are marked; the change goes into the shell's draft, not to the server.
 */
export function SettingRow({field}: {field: SettingField}) {
  const {t} = useIntl();
  const {settings, form, setValue} = useSearchState();
  if (!settings) return null;
  const value = form[field.key];
  const fallback = settings.defaults[field.key];
  const changed = !sameValue(value, settings.values[field.key]);
  const nondefault = !sameValue(value, fallback);
  return (
    <div className={'row' + (changed ? ' changed' : '') + (nondefault ? ' nondefault' : '')} id={'row-' + field.key}>
      <div>
        <div className="lab" title={field.key}>
          {field.label}
          {field.effect === 'reindex' ? (
            <span className="eff" title={t('settings.reindexTip')}>
              {t('settings.reindex')}
            </span>
          ) : null}
        </div>
        {field.help ? (
          <div className="help" title={field.help}>
            {field.help}
          </div>
        ) : null}
      </div>
      <div className="ctl">
        <Control field={field} value={value} onChange={(next) => setValue(field.key, next)} />
        <button
          className="reset"
          type="button"
          title={t('settings.resetTip', {value: showValue(field, fallback, t('settings.empty'))})}
          aria-label={t('settings.reset')}
          onClick={() => setValue(field.key, fallback)}
        >
          ↺
        </button>
      </div>
    </div>
  );
}
