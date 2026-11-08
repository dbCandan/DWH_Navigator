import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {RecordEditor} from './RecordEditor';
import {ScoreCard} from './ScoreCard';
import {IntlProvider} from '@/contexts/IntlContext';
import {message} from '@/test/render';
import type {SyncScore} from '@/types/dictionarySync';

const SCORE: SyncScore = {
  score: 82,
  verdict: 'incelenmeli',
  failed_checks: ['belirsizlik'],
  checks: {belirsizlik: {count: 2, examples: ['EDWDM.CRP.vRate.Amount']}},
  judge: {
    sample: 40,
    population: 120,
    right: 33,
    minor: 4,
    wrong: 3,
    wrong_interval: [0.026, 0.199],
    failures: 0,
    wrong_rows: [{table: 'EDWDM.CRP.vRate', column: 'Amount', verdict: 'hatali', reason: 'Adet, bayrak değil.'}],
  },
  model: {calls: 160, failures: 2, failure_rate: 0.013},
  rules: {normalized_fields: 14},
};

describe('score card (dictionary curation)', () => {
  it('shows the score, the recommendation, the failed checks and the misleading rows', () => {
    const onFix = vi.fn();
    render(
      <IntlProvider>
        <ScoreCard score={SCORE} editable onFix={onFix} />
      </IntlProvider>,
    );
    expect(screen.getByText('82')).toBeTruthy();
    expect(screen.getByText(message('dictionary.score.verdict.incelenmeli'))).toBeTruthy();
    expect(screen.getByText(/EDWDM\.CRP\.vRate\.Amount/)).toBeTruthy();
    expect(screen.getByText('Adet, bayrak değil.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.edit.open')}));
    expect(onFix).toHaveBeenCalledWith(SCORE.judge?.wrong_rows[0]);
  });

  it('offers no fix when the run does not wait for approval, and nothing for an old run', () => {
    const {container, rerender} = render(
      <IntlProvider>
        <ScoreCard score={SCORE} editable={false} onFix={vi.fn()} />
      </IntlProvider>,
    );
    expect(screen.queryByRole('button', {name: message('dictionary.edit.open')})).toBeNull();
    rerender(
      <IntlProvider>
        <ScoreCard score={{}} editable onFix={vi.fn()} />
      </IntlProvider>,
    );
    expect(container.querySelector('#d-score')).toBeNull();
  });
});

describe('record editor (dictionary curation)', () => {
  it('saves the admin text for the chosen field', () => {
    const onSave = vi.fn();
    render(
      <IntlProvider>
        <RecordEditor tableKey="EDWDM.CRP.vRate" columnName="Amount" field="Summary" value="Tutar" busy={false} onSave={onSave} onCancel={vi.fn()} />
      </IntlProvider>,
    );
    fireEvent.change(screen.getByRole('textbox'), {target: {value: '  Kayıt adedi  '}});
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.edit.save')}));
    expect(onSave).toHaveBeenCalledWith({table_key: 'EDWDM.CRP.vRate', column_name: 'Amount', field: 'Summary', value: 'Kayıt adedi'});
  });

  it('refuses a summary over 70 characters and an empty description', () => {
    const onSave = vi.fn();
    render(
      <IntlProvider>
        <RecordEditor tableKey="EDWDM.CRP.vRate" columnName="Amount" field="Summary" value={'x'.repeat(71)} busy={false} onSave={onSave} onCancel={vi.fn()} />
      </IntlProvider>,
    );
    const save = screen.getByRole('button', {name: message('dictionary.edit.save')}) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByRole('combobox'), {target: {value: 'ColumnDescription'}});
    fireEvent.change(screen.getByRole('textbox'), {target: {value: ''}});
    expect(save.disabled).toBe(true);
    expect(onSave).not.toHaveBeenCalled();
  });

  it('lists only object fields for an object record', () => {
    render(
      <IntlProvider>
        <RecordEditor tableKey="EDWDM.CRP.vRate" columnName="" busy={false} onSave={vi.fn()} onCancel={vi.fn()} />
      </IntlProvider>,
    );
    const options = Array.from(screen.getByRole('combobox').querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['ObjectDescription', 'Grain', 'KeyColumns', 'TimeColumns', 'BusinessDomain']);
  });
});

describe('record editor roles', () => {
  it('starts a role from a fixed name, never from an empty choice', () => {
    const onSave = vi.fn();
    render(
      <IntlProvider>
        <RecordEditor tableKey="EDWDM.CRP.vRate" columnName="Amount" field="Role" value="" busy={false} onSave={onSave} onCancel={vi.fn()} />
      </IntlProvider>,
    );
    const role = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    expect(Array.from(role.querySelectorAll('option')).map((o) => o.value)).not.toContain('');
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.edit.save')}));
    expect(onSave).toHaveBeenCalledWith({table_key: 'EDWDM.CRP.vRate', column_name: 'Amount', field: 'Role', value: 'Anahtar'});
  });
});
