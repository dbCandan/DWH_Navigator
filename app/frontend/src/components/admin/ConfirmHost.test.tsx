import {act, fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {IntlProvider} from '@/contexts/IntlContext';
import {confirmAction} from '@/lib/confirm';
import {message} from '@/test/render';
import {ConfirmHost} from './ConfirmHost';

function mount() {
  render(
    <IntlProvider>
      <ConfirmHost />
    </IntlProvider>,
  );
}

describe('the admin confirmation dialog', () => {
  it('asks with the question as title, the rest as text and the step\'s own verb', async () => {
    mount();
    let answer: Promise<boolean> | undefined;
    act(() => {
      answer = confirmAction('Silinsin mi?\n\nGeri alınamaz.', {action: 'Sil', danger: true});
    });
    const dialog = await screen.findByRole('alertdialog', {name: 'Silinsin mi?'});
    expect(dialog).toHaveAccessibleDescription('Geri alınamaz.');
    expect(screen.getByRole('button', {name: message('admin.confirm.cancel')})).toHaveFocus();
    fireEvent.click(screen.getByRole('button', {name: 'Sil'}));
    await expect(answer).resolves.toBe(true);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('says no on Esc and on a click outside, one question at a time', async () => {
    mount();
    let first: Promise<boolean> | undefined;
    let second: Promise<boolean> | undefined;
    act(() => {
      first = confirmAction('Birinci?');
      second = confirmAction('İkinci?');
    });
    const dialog = await screen.findByRole('alertdialog', {name: 'Birinci?'});
    expect(screen.getByRole('button', {name: message('admin.confirm.ok')})).toHaveFocus();
    fireEvent.keyDown(dialog, {key: 'Escape'});
    await expect(first).resolves.toBe(false);
    await screen.findByRole('alertdialog', {name: 'İkinci?'});
    fireEvent.click(document.querySelector('.confirm') as HTMLElement);
    await expect(second).resolves.toBe(false);
  });
});
