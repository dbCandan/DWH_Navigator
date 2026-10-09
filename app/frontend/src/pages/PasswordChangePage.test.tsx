import {fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth, readAccessToken} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import {message, renderApp, signedIn} from '@/test/render';

function fill(current: string, next: string, repeat = next) {
  fireEvent.change(screen.getByLabelText(message('auth.password.current')), {target: {value: current}});
  fireEvent.change(screen.getByLabelText(message('auth.password.new')), {target: {value: next}});
  fireEvent.change(screen.getByLabelText(message('auth.password.repeat')), {target: {value: repeat}});
  fireEvent.click(screen.getByRole('button', {name: message('auth.password.submit')}));
}

describe('"Parolamı değiştir" (user-accounts Requirement 4 and 16)', () => {
  beforeEach(() => signedIn('user'));
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('changes the password with the current one and keeps the new session', async () => {
    const user = signedIn('user');
    const change = vi
      .spyOn(AuthService, 'changePassword')
      .mockResolvedValue({access_token: 'renewed', token_type: 'bearer', expires_in: 900, user});
    renderApp('/parola');
    await screen.findByRole('heading', {name: message('auth.password.title')});
    fill('şimdiki parola', 'yepyeni ve uzun bir parola');
    expect((await screen.findByRole('status')).textContent).toBe(message('auth.password.changed'));
    expect(change).toHaveBeenCalledWith('ayse.yilmaz', 'şimdiki parola', 'yepyeni ve uzun bir parola');
    expect(readAccessToken()).toBe('renewed');
    expect(screen.getByRole('link', {name: message('auth.password.back')})).toHaveAttribute('href', '/');
  });

  it.each([
    ['a wrong current password', new ApiError(401, 'x', 'invalid_credentials'), message('auth.error.wrongCurrentPassword')],
    ['the policy', new ApiError(422, 'Bu parola çok yaygın ya da kolay tahmin edilir; başka bir parola seçin.', 'password_policy'), 'Bu parola çok yaygın ya da kolay tahmin edilir; başka bir parola seçin.'],
    ['an unexpected failure', new ApiError(500, 'Sunucu hatası', 'internal_error'), message('auth.error.unavailable')],
  ])('explains %s', async (_, failure, text) => {
    vi.spyOn(AuthService, 'changePassword').mockRejectedValue(failure);
    renderApp('/parola');
    await screen.findByRole('heading', {name: message('auth.password.title')});
    fill('şimdiki parola', 'yepyeni ve uzun bir parola');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe(text));
    expect(readAccessToken()).toBe('token');
  });

  it('refuses a repeat that differs without calling the server', async () => {
    const change = vi.spyOn(AuthService, 'changePassword');
    renderApp('/parola');
    await screen.findByRole('heading', {name: message('auth.password.title')});
    fill('şimdiki', 'yepyeni ve uzun bir parola', 'başka');
    expect((await screen.findByRole('alert')).textContent).toBe(message('auth.password.mismatch'));
    expect(change).not.toHaveBeenCalled();
  });
});
