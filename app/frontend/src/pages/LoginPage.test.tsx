import {fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth, readAccessToken} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import {message, renderApp, ROLES} from '@/test/render';
import type {LoginResponse} from '@/types/auth';

const session = (token = 'jwt'): LoginResponse => ({
  access_token: token,
  token_type: 'bearer',
  expires_in: 900,
  user: {
    public_id: '00000000-0000-4000-8000-000000000002',
    username: 'ad.soyad',
    display_name: 'Ad Soyad',
    tenant_id: '00000000-0000-4000-8000-0000000000aa',
    permissions: [],
    ...ROLES.user,
  },
});

async function openLogin(path = '/') {
  renderApp(path);
  await screen.findByRole('heading', {name: message('auth.login.title')});
}

function signIn(username = 'ad.soyad', password = 'tek kullanımlık') {
  fireEvent.change(screen.getByLabelText(message('auth.login.username')), {target: {value: username}});
  fireEvent.change(screen.getByLabelText(message('auth.login.password')), {target: {value: password}});
  fireEvent.click(screen.getByRole('button', {name: message('auth.login.submit')}));
}

describe('sign-in (user-accounts Requirement 1 and 16)', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'x', 'session_expired', true));
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('sends a signed-out visitor to the sign-in screen and back to the page afterwards', async () => {
    vi.spyOn(AuthService, 'login').mockResolvedValue(session());
    await openLogin('/parola');
    expect(screen.getByTestId('where').textContent).toBe('/login');
    signIn();
    await screen.findByRole('heading', {name: message('auth.password.title')});
    expect(screen.getByTestId('where').textContent).toBe('/parola');
    expect(readAccessToken()).toBe('jwt');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it.each([
    ['a wrong user name or password', new ApiError(401, 'x', 'invalid_credentials'), message('auth.error.invalidCredentials')],
    ['an inactive account', new ApiError(403, 'x', 'user_inactive'), message('auth.error.inactive')],
    ['an expired one-time password', new ApiError(401, 'x', 'one_time_password_expired'), message('auth.error.oneTimeExpired')],
    [
      'too many attempts',
      new ApiError(429, 'x', 'rate_limited', false, 300),
      message('auth.error.tooManyAttemptsMinutes', {minutes: 5}),
    ],
    ['too many attempts, seconds', new ApiError(429, 'x', 'rate_limited', false, 40), message('auth.error.tooManyAttemptsSeconds', {seconds: 40})],
    ['a lost connection', new TypeError('Failed to fetch'), message('auth.error.unavailable')],
  ])('explains %s', async (_, failure, text) => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(failure);
    await openLogin('/login');
    signIn();
    expect((await screen.findByRole('alert')).textContent).toBe(text);
    expect(readAccessToken()).toBeNull();
  });

  it('asks for a new password when the account still holds its one-time password', async () => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new ApiError(403, 'x', 'password_change_required'));
    const change = vi.spyOn(AuthService, 'changePassword');
    change
      .mockRejectedValueOnce(new ApiError(422, 'Parola en az 15 karakter olmalı; uzun bir cümle seçebilirsiniz.', 'password_policy'))
      .mockResolvedValueOnce(session('after-change'));
    await openLogin('/login');
    signIn('ad.soyad', 'tek-kullanimlik-parola');
    await screen.findByRole('heading', {name: message('auth.firstLogin.title')});
    expect(screen.getByText(message('auth.password.policy'))).toBeInTheDocument();
    const next = screen.getByLabelText(message('auth.password.new'));
    expect(next).toHaveAccessibleDescription(message('auth.password.policy'));

    fireEvent.change(next, {target: {value: 'kısa parola'}});
    fireEvent.change(screen.getByLabelText(message('auth.password.repeat')), {target: {value: 'başka'}});
    fireEvent.click(screen.getByRole('button', {name: message('auth.firstLogin.submit')}));
    expect((await screen.findByRole('alert')).textContent).toBe(message('auth.password.mismatch'));
    expect(change).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(message('auth.password.repeat')), {target: {value: 'kısa parola'}});
    fireEvent.click(screen.getByRole('button', {name: message('auth.firstLogin.submit')}));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Parola en az 15 karakter olmalı; uzun bir cümle seçebilirsiniz.'));

    const chosen = 'mavi gökyüzünde uçan yıldızlar';
    fireEvent.change(next, {target: {value: chosen}});
    fireEvent.change(screen.getByLabelText(message('auth.password.repeat')), {target: {value: chosen}});
    fireEvent.click(screen.getByRole('button', {name: message('auth.firstLogin.submit')}));
    await waitFor(() => expect(readAccessToken()).toBe('after-change'));
    expect(change).toHaveBeenLastCalledWith('ad.soyad', 'tek-kullanimlik-parola', chosen);
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/'));
  });
});
