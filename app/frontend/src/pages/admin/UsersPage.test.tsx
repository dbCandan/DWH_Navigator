import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {UserAdminService} from '@/services/userAdmin';
import {llmState} from '@/test/llm';
import {message, renderApp, signedIn} from '@/test/render';
import type {UserSummary} from '@/types/auth';

const account = (username: string, overrides: Partial<UserSummary> = {}): UserSummary => ({
  public_id: `id-${username}`,
  username,
  display_name: username.replace('.', ' '),
  role: 'kullanici',
  active: true,
  password_change_required: false,
  last_login_at: null,
  created_at: '2026-10-08T08:00:00Z',
  ...overrides,
});

const SUPER = account('super-admin', {role: 'super_admin', public_id: '00000000-0000-4000-8000-000000000001'});
const ALI = account('ali.kaya', {password_change_required: true});
const page = (items: UserSummary[]) => ({items, page: 1, size: 50, total: items.length});
const ONE_TIME = 'k7m2q9w4x8r3t6y5u2p4';

/** The browser's confirmation dialog, answered by the test. */
function answerConfirm(...answers: boolean[]) {
  const confirm = vi.fn(() => answers.length > 1 ? (answers.shift() as boolean) : answers[0]);
  Object.defineProperty(window, 'confirm', {value: confirm, configurable: true, writable: true});
  return confirm;
}

async function openUsers() {
  renderApp('/admin/kullanicilar');
  return screen.findByRole('table');
}

describe('Kullanıcılar (user-accounts Requirement 16)', () => {
  beforeEach(() => {
    signedIn('super');
    vi.spyOn(UserAdminService, 'list').mockResolvedValue(page([ALI, SUPER]));
    vi.spyOn(LlmIntegrationService, 'list').mockResolvedValue(llmState());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('lists the accounts and protects the super admin rows', async () => {
    const table = await openUsers();
    const rows = within(table).getAllByRole('row');
    expect(within(rows[1]).getByRole('combobox', {name: message('users.roleOf', {username: 'ali.kaya'})})).toHaveValue('kullanici');
    expect(within(rows[1]).getByText(message('users.status.newPassword'))).toBeInTheDocument();
    expect(within(rows[1]).getByRole('button', {name: message('users.deactivate')})).toBeInTheDocument();
    expect(within(rows[2]).getByText(message('users.role.superAdmin'))).toBeInTheDocument();
    expect(within(rows[2]).queryByRole('button')).toBeNull();
    expect(within(rows[2]).queryByRole('combobox')).toBeNull();
  });

  it('searches by user name and display name', async () => {
    await openUsers();
    fireEvent.change(screen.getByRole('searchbox', {name: message('users.search.label')}), {target: {value: 'ali'}});
    await waitFor(() => expect(UserAdminService.list).toHaveBeenLastCalledWith({page: 1, size: 50, q: 'ali'}));
  });

  it('shows a new account\'s one-time password once, with copy and expiry, and forgets it on close', async () => {
    const create = vi.spyOn(UserAdminService, 'create').mockResolvedValue({
      user: account('yeni.kisi'),
      one_time_password: ONE_TIME,
      one_time_password_expires_at: '2026-10-11T08:00:00Z',
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {value: {writeText}, configurable: true});
    await openUsers();
    fireEvent.click(screen.getByRole('button', {name: message('users.add')}));
    const form = await screen.findByRole('dialog', {name: message('users.add')});
    fireEvent.change(within(form).getByLabelText(message('users.column.username')), {target: {value: 'yeni.kisi'}});
    fireEvent.change(within(form).getByLabelText(message('users.column.displayName')), {target: {value: 'Yeni Kişi'}});
    fireEvent.change(within(form).getByLabelText(message('users.column.role')), {target: {value: 'yonetici'}});
    fireEvent.click(within(form).getByRole('button', {name: message('users.create')}));

    const shown = await screen.findByRole('dialog', {name: message('users.secret.title')});
    expect(create).toHaveBeenCalledWith({username: 'yeni.kisi', display_name: 'Yeni Kişi', role: 'yonetici'});
    expect(within(shown).getByText(ONE_TIME)).toBeInTheDocument();
    expect(within(shown).getByText(message('users.secret.once'))).toBeInTheDocument();
    await act(async () => fireEvent.click(within(shown).getByRole('button', {name: message('users.secret.copy')})));
    expect(writeText).toHaveBeenCalledWith(ONE_TIME);
    expect(within(shown).getByRole('button', {name: message('users.secret.copied')})).toBeInTheDocument();

    fireEvent.click(within(shown).getByRole('button', {name: message('users.secret.done')}));
    expect(screen.queryByText(ONE_TIME)).toBeNull();
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });

  it('explains a taken user name inside the form', async () => {
    vi.spyOn(UserAdminService, 'create').mockRejectedValue(new ApiError(409, 'x', 'username_taken'));
    await openUsers();
    fireEvent.click(screen.getByRole('button', {name: message('users.add')}));
    const form = await screen.findByRole('dialog', {name: message('users.add')});
    fireEvent.change(within(form).getByLabelText(message('users.column.username')), {target: {value: 'ali.kaya'}});
    fireEvent.change(within(form).getByLabelText(message('users.column.displayName')), {target: {value: 'Ali'}});
    fireEvent.click(within(form).getByRole('button', {name: message('users.create')}));
    expect((await within(form).findByRole('alert')).textContent).toBe(message('users.error.usernameTaken'));
  });

  it('asks before a role change and does nothing when declined', async () => {
    const setRole = vi.spyOn(UserAdminService, 'setRole').mockResolvedValue({role: 'yonetici'});
    const confirm = answerConfirm(false, true);
    await openUsers();
    const select = screen.getByRole('combobox', {name: message('users.roleOf', {username: 'ali.kaya'})});
    fireEvent.change(select, {target: {value: 'yonetici'}});
    expect(confirm).toHaveBeenCalledWith(message('users.confirm.role', {username: 'ali.kaya', role: message('users.role.manager')}));
    expect(setRole).not.toHaveBeenCalled();
    fireEvent.change(select, {target: {value: 'yonetici'}});
    await waitFor(() => expect(setRole).toHaveBeenCalledWith(ALI, 'yonetici'));
    expect(await screen.findByText(message('users.done.role', {username: 'ali.kaya', role: message('users.role.manager')}))).toBeInTheDocument();
  });

  it('asks before deactivating and before a reset; a reset shows the new password once', async () => {
    const setActive = vi.spyOn(UserAdminService, 'setActive').mockResolvedValue({active: false});
    const reset = vi
      .spyOn(UserAdminService, 'resetPassword')
      .mockResolvedValue({one_time_password: ONE_TIME, one_time_password_expires_at: '2026-10-11T08:00:00Z'});
    const confirm = answerConfirm(true);
    await openUsers();
    fireEvent.click(screen.getByRole('button', {name: message('users.deactivate')}));
    expect(confirm).toHaveBeenLastCalledWith(message('users.confirm.deactivate', {username: 'ali.kaya'}));
    await waitFor(() => expect(setActive).toHaveBeenCalledWith(ALI, false));

    fireEvent.click(screen.getByRole('button', {name: message('users.reset')}));
    expect(confirm).toHaveBeenLastCalledWith(message('users.confirm.reset', {username: 'ali.kaya'}));
    const shown = await screen.findByRole('dialog', {name: message('users.secret.title')});
    expect(reset).toHaveBeenCalledWith(ALI);
    expect(within(shown).getByText(ONE_TIME)).toBeInTheDocument();
  });

  it('reports a lost connection with the admin screen\'s notice', async () => {
    vi.spyOn(UserAdminService, 'list').mockRejectedValue(new TypeError('Failed to fetch'));
    renderApp('/admin/kullanicilar');
    expect(await screen.findByText(message('admin.unreachable.title'))).toBeInTheDocument();
    expect(screen.getByText(message('users.loadFailed'))).toBeInTheDocument();
  });
});
