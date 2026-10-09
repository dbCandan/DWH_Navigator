import {apiRequest, refreshSession} from '@/lib/apiClient';
import type {AuthenticatedUser, LoginResponse} from '@/types/auth';

/** Local accounts and sessions (user-accounts Requirement 1, 4, 6-8). */
export const AuthService = {
  login(username: string, password: string): Promise<LoginResponse> {
    return apiRequest<LoginResponse>(
      '/auth/login',
      {method: 'POST', body: JSON.stringify({username, password}), credentials: 'same-origin'},
      false,
    );
  },
  /**
   * Set a new password with the current (or one-time) one; the answer is a new session, as for
   * login. The first sign-in's required change and a voluntary change use this one call.
   */
  changePassword(username: string, currentPassword: string, newPassword: string): Promise<LoginResponse> {
    return apiRequest<LoginResponse>(
      '/auth/password',
      {
        method: 'POST',
        body: JSON.stringify({username, current_password: currentPassword, new_password: newPassword}),
        credentials: 'same-origin',
      },
      false,
    );
  },
  /** Restore or renew the session from the HttpOnly refresh cookie. */
  refresh(): Promise<LoginResponse> {
    return refreshSession();
  },
  /** End the refresh session on the server; the response removes the cookie. */
  logout(): Promise<void> {
    return apiRequest<void>('/auth/logout', {method: 'POST', credentials: 'same-origin'}, false);
  },
  me(): Promise<AuthenticatedUser> {
    return apiRequest<AuthenticatedUser>('/auth/me');
  },
};
