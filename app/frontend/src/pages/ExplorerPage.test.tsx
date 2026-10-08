import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, readAccessToken} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import {message, renderApp, signedIn} from '@/test/render';

async function openExplorer(kind: 'user' | 'manager' | 'super' = 'user') {
  signedIn(kind, 'Ayşe Yılmaz');
  renderApp('/');
  return screen.findByRole('banner');
}

describe('main screen shell (dictionary-explorer Requirement 1, 15, 17)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
    document.documentElement.className = '';
  });

  it('shows the brand, the landing title and the question bar in the source\'s structure', async () => {
    await openExplorer();
    expect(document.documentElement.dataset.surface).toBe('explorer');
    expect(document.title).toBe(message('explorer.documentTitle'));
    const brand = screen.getByRole('link', {name: /DWH Navigator/});
    expect(brand).toHaveAttribute('href', '/');
    expect(brand).toHaveAttribute('title', message('explorer.brand.restart'));
    expect(brand).toHaveClass('brand');
    expect(screen.getByRole('heading', {level: 1, name: message('explorer.hero.title')})).toBeInTheDocument();
    const question = screen.getByRole('textbox', {name: message('explorer.search.label')});
    expect(question).toHaveAttribute('id', 'q');
    expect(question.closest('#hero > .searchbox')).not.toBeNull();
    expect(document.querySelector('header.top .wrap > #bar-slot.slot')).not.toBeNull();
    expect(document.querySelector('header.top .tools > #status.status')).not.toBeNull();
    expect(document.querySelector('#cosmos')).toHaveAttribute('aria-hidden', 'true');
  });

  it.each(['user', 'manager', 'super'] as const)('offers no link to the admin screen (%s)', async (kind) => {
    await openExplorer(kind);
    for (const link of screen.getAllByRole('link')) expect(link.getAttribute('href')).not.toMatch(/admin/);
  });

  it('shows the session area with the name, "Parolamı değiştir" and "Çıkış"', async () => {
    const logout = vi.spyOn(AuthService, 'logout').mockResolvedValue(undefined);
    await openExplorer();
    const toggle = screen.getByRole('button', {name: message('session.menu', {name: 'Ayşe Yılmaz'})});
    expect(toggle).toHaveClass('pill');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', {name: message('session.changePassword')})).toHaveAttribute('href', '/parola');
    fireEvent.keyDown(document, {key: 'Escape'});
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(toggle);
    fireEvent.click(toggle);
    await act(async () => fireEvent.click(screen.getByRole('button', {name: message('session.signOut')})));
    expect(logout).toHaveBeenCalled();
    expect(readAccessToken()).toBeNull();
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/login'));
  });

  it('starts over from the brand without leaving the page', async () => {
    await openExplorer();
    const question = screen.getByRole('textbox', {name: message('explorer.search.label')});
    fireEvent.change(question, {target: {value: 'kredi kartı limiti'}});
    fireEvent.click(screen.getByRole('link', {name: /DWH Navigator/}));
    expect(question).toHaveValue('');
    expect(screen.getByTestId('where').textContent).toBe('/');
  });

  it('puts the veil behind the top line and moves the HUD aside as the page scrolls', async () => {
    await openExplorer();
    const root = document.documentElement;
    Object.defineProperty(window, 'scrollY', {value: 200, configurable: true});
    await act(async () => window.dispatchEvent(new Event('scroll')));
    expect(root).toHaveClass('lifted');
    expect(root).toHaveClass('scrolled');
    Object.defineProperty(window, 'scrollY', {value: 0, configurable: true});
    await act(async () => window.dispatchEvent(new Event('scroll')));
    expect(root).not.toHaveClass('lifted');
  });

  it('keeps every control reachable from the keyboard', async () => {
    await openExplorer();
    const controls = [...document.querySelectorAll<HTMLElement>('a[href], button, textarea')];
    expect(controls.length).toBeGreaterThan(3);
    for (const control of controls) expect(control.tabIndex).toBeGreaterThanOrEqual(0);
  });
});
