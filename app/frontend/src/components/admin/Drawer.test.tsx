import {fireEvent, render, screen} from '@testing-library/react';
import {useState} from 'react';
import {describe, expect, it} from 'vitest';
import {Drawer} from './Drawer';
import {IntlProvider} from '@/contexts/IntlContext';
import {message} from '@/test/render';

function Host() {
  const [open, setOpen] = useState(false);
  return (
    <IntlProvider>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      {open && (
        <Drawer title="Ayrıntı" sub="alt yazı" onClose={() => setOpen(false)} foot={<button type="button">son</button>}>
          <input aria-label="ilk" />
        </Drawer>
      )}
    </IntlProvider>
  );
}

describe('drawer (search-settings Requirement 24)', () => {
  it('focuses its first field, keeps Tab inside, closes on Esc and returns the focus', () => {
    render(<Host />);
    const opener = screen.getByRole('button', {name: 'open'});
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole('dialog', {name: 'Ayrıntı'});
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const field = screen.getByRole('textbox', {name: 'ilk'});
    expect(document.activeElement).toBe(field);

    const last = screen.getByRole('button', {name: 'son'});
    last.focus();
    fireEvent.keyDown(last, {key: 'Tab'});
    expect(document.activeElement).toBe(screen.getByRole('button', {name: message('admin.drawer.close')}));
    fireEvent.keyDown(document.activeElement as Element, {key: 'Tab', shiftKey: true});
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('closes with "Kapat (Esc)" and with a click outside the panel', () => {
    render(<Host />);
    fireEvent.click(screen.getByRole('button', {name: 'open'}));
    fireEvent.click(screen.getByRole('button', {name: message('admin.drawer.close')}));
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'open'}));
    fireEvent.click(document.querySelector('.drawer') as Element);
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
