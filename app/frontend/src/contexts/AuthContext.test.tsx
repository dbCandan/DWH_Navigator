import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {AuthProvider, useAuth} from './AuthContext';
import {ApiError} from '@/lib/apiClient';
import {clearAuth, readAccessToken, writeSession} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import type {AuthenticatedUser} from '@/types/auth';

const restored = {
  public_id: 'p1',
  username: 'ad.soyad',
  display_name: 'Ad Soyad',
  tenant_id: 't1',
  role: 'yonetici',
} as AuthenticatedUser;

function Probe() {
  const {user, loading, access, logout} = useAuth();
  return (
    <>
      <p data-testid="session">{loading ? 'loading' : (user?.username ?? 'signed-out')}</p>
      <p data-testid="access">{`${access.administer}/${access.manageUsers}`}</p>
      <button type="button" onClick={() => void logout()}>
        out
      </button>
    </>
  );
}

const signedIn = (role: 'super_admin' | 'kullanici') =>
  writeSession('token', {...restored, role, roles: [role], is_super_admin: role === 'super_admin'});

const show = () =>
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );

describe('session (user-accounts Requirement 6-8)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('restores the session from the refresh cookie when the page loads', async () => {
    const refresh = vi.spyOn(AuthService, 'refresh').mockImplementation(async () => {
      writeSession('fresh', restored);
      return {access_token: 'fresh', token_type: 'bearer', expires_in: 900, user: restored};
    });
    show();
    expect(screen.getByTestId('session').textContent).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('session').textContent).toBe('ad.soyad'));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('access').textContent).toBe('true/false');
  });

  it('stays signed out when there is no session to restore', async () => {
    vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'x', 'session_expired', true));
    show();
    await waitFor(() => expect(screen.getByTestId('session').textContent).toBe('signed-out'));
  });

  it('closes the server session and forgets the token on sign-out, even when the call fails', async () => {
    signedIn('super_admin');
    const logout = vi.spyOn(AuthService, 'logout').mockRejectedValue(new TypeError('Failed to fetch'));
    show();
    expect(screen.getByTestId('access').textContent).toBe('true/true');
    await act(async () => fireEvent.click(screen.getByRole('button', {name: 'out'})));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(readAccessToken()).toBeNull();
    expect(screen.getByTestId('session').textContent).toBe('signed-out');
  });

  it('gives the admin screen to yonetici and the super admin only', () => {
    signedIn('kullanici');
    show();
    expect(screen.getByTestId('access').textContent).toBe('false/false');
  });
});
