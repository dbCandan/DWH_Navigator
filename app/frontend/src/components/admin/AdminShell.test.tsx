import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {NAV_PAGES} from './nav';
import {clearAuth} from '@/lib/authStorage';
import messages from '@/locales/tr.json';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {UserAdminService} from '@/services/userAdmin';
import {llmState} from '@/test/llm';
import {message, renderApp, signedIn} from '@/test/render';

const label = (id: string) => message(`admin.page.${id}.label`);

async function openAdmin(path: string) {
  renderApp(path);
  return screen.findByRole('navigation', {name: message('admin.nav.label')});
}

describe('admin shell (search-settings Requirement 20-22, 24)', () => {
  beforeEach(() => {
    vi.spyOn(UserAdminService, 'list').mockResolvedValue({items: [], page: 1, size: 50, total: 0});
    vi.spyOn(LlmIntegrationService, 'list').mockResolvedValue(llmState());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('has a label, a tooltip and a description for every page in the catalog', () => {
    for (const page of NAV_PAGES)
      for (const part of ['label', 'tip', 'description'])
        expect(Object.keys(messages)).toContain(`admin.page.${page.id}.${part}`);
  });

  it('sends /admin to Genel bakış, marks the page and titles the tab', async () => {
    signedIn('manager');
    const nav = await openAdmin('/admin');
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/genel'));
    expect(within(nav).getByRole('link', {name: label('genel')})).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', {level: 1, name: label('genel')})).toBeInTheDocument();
    expect(document.title).toBe(message('admin.documentTitle', {page: label('genel')}));
    expect(document.documentElement.dataset.surface).toBe('admin');
  });

  it('shows the three groups, seven pages and the session area to yonetici', async () => {
    signedIn('manager', 'Ayşe Yılmaz');
    const nav = await openAdmin('/admin/bakim');
    for (const group of ['admin.nav.monitoring', 'admin.nav.data', 'admin.nav.settings'])
      expect(within(nav).getByText(message(group))).toBeInTheDocument();
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.querySelector('.lbl')?.textContent)).toEqual(NAV_PAGES.filter((p) => !p.superAdmin).map((p) => label(p.id)));
    expect(within(nav).getByRole('link', {name: label('bakim')})).toHaveAttribute('title', message('admin.page.bakim.tip'));
    expect(screen.getByText('Ayşe Yılmaz')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: message('session.changePassword')})).toHaveAttribute('href', '/parola');
    expect(screen.getByRole('button', {name: message('session.signOut')})).toBeInTheDocument();
    expect(screen.getByRole('link', {name: message('admin.back')})).toHaveAttribute('href', '/');
  });

  it('adds Kullanıcılar for the super admin only', async () => {
    signedIn('super');
    const nav = await openAdmin('/admin/genel');
    expect(within(nav).getByRole('link', {name: label('kullanicilar')})).toHaveAttribute('href', '/admin/kullanicilar');
  });

  it('turns a yonetici away from Kullanıcılar', async () => {
    signedIn('manager');
    renderApp('/admin/kullanicilar');
    expect(await screen.findByRole('heading', {name: message('access.forbidden.title')})).toBeInTheDocument();
    expect(UserAdminService.list).not.toHaveBeenCalled();
  });

  it('shows kullanici the "no access" screen instead of the admin screen', async () => {
    signedIn('user');
    renderApp('/admin/genel');
    expect(await screen.findByRole('heading', {name: message('access.forbidden.title')})).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).toBeNull();
  });

  it('opens item addresses on their page and answers an unknown address with "not found"', async () => {
    signedIn('manager');
    const view = renderApp('/admin/sozluk/DWH.Ornek.vCustomerInfo');
    expect(await screen.findByRole('heading', {level: 1, name: label('sozluk')})).toBeInTheDocument();
    view.unmount();
    renderApp('/admin/analizler/0b6f6f3e-3e0a-4c58-9a3a-8a2f9c1e2d11');
    expect(await screen.findByRole('heading', {level: 1, name: label('analizler')})).toBeInTheDocument();
  });

  it('answers an unknown /admin address with the application\'s "not found"', async () => {
    signedIn('manager');
    renderApp('/admin/yok-boyle');
    expect(await screen.findByRole('heading', {name: message('routing.notFound.title')})).toBeInTheDocument();
  });

  it('opens the command palette with Ctrl K and the button, filters, moves with the arrows and runs with Enter', async () => {
    signedIn('super');
    await openAdmin('/admin/genel');
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    const box = await screen.findByRole('textbox', {name: message('admin.palette.label')});
    expect(box).toHaveAttribute('placeholder', message('admin.palette.placeholder'));
    expect(screen.getByText(message('admin.palette.pages'))).toBeInTheDocument();
    expect(screen.getByText(message('admin.palette.actions'))).toBeInTheDocument();
    // The pages, then the dictionary's three, the index rebuild, "Yeni model entegrasyonu",
    // "Model envanteri", "Performans ayrıntıları" and "Uygulamaya dön".
    expect(screen.getAllByRole('option')).toHaveLength(NAV_PAGES.length + 8);

    fireEvent.change(box, {target: {value: 'kullanici'}});
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual([
      label('kullanicilar') + message('admin.page.kullanicilar.tip'),
    ]);
    fireEvent.change(box, {target: {value: 'zzzz'}});
    expect(screen.getByText(message('admin.palette.empty'))).toBeInTheDocument();

    fireEvent.change(box, {target: {value: ''}});
    fireEvent.keyDown(box, {key: 'ArrowDown'});
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(box, {key: 'Enter'});
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/analizler'));
    expect(screen.queryByRole('textbox', {name: message('admin.palette.label')})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: message('admin.palette.open')}));
    const again = await screen.findByRole('textbox', {name: message('admin.palette.label')});
    fireEvent.keyDown(again, {key: 'Escape'});
    expect(screen.queryByRole('textbox', {name: message('admin.palette.label')})).toBeNull();

    fireEvent.keyDown(window, {key: 'k', metaKey: true});
    expect(await screen.findByRole('textbox', {name: message('admin.palette.label')})).toBeInTheDocument();
    fireEvent.keyDown(window, {key: 'k', metaKey: true});
    expect(screen.queryByRole('textbox', {name: message('admin.palette.label')})).toBeNull();
  });

  it('moves the keyboard to the page\'s search field with "/" when nothing else has it', async () => {
    signedIn('super');
    renderApp('/admin/kullanicilar');
    const search = await screen.findByRole('searchbox', {name: message('users.search.label')});
    fireEvent.keyDown(document.body, {key: '/'});
    expect(document.activeElement).toBe(search);
  });
});
