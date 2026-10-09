import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import {accessOf, type Access} from '@/lib/access';
import {clearAuth, readUser, subscribeAuth, writeSession} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import type {AuthenticatedUser} from '@/types/auth';

interface AuthValue {
  user: AuthenticatedUser | null;
  /** True while a page load restores the session from the refresh cookie. */
  loading: boolean;
  /** Menu and route visibility only; the backend authorizes every request. */
  access: Access;
  login: (username: string, password: string) => Promise<void>;
  /** Set a new password with the current (or one-time) one and keep the new session. */
  changePassword: (username: string, currentPassword: string, newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const Context = createContext<AuthValue | null>(null);

/**
 * The signed-in session (user-accounts Requirement 6-8, 16; rules/34). The token and the user live
 * in memory only, so every page load first restores the session from the HttpOnly refresh cookie
 * before protected routes render; a failed refresh (401) leaves the user signed out, which sends
 * protected routes to the sign-in screen.
 */
export function AuthProvider({children}: {children: ReactNode}) {
  const user = useSyncExternalStore(subscribeAuth, readUser, readUser);
  const [restoring, setRestoring] = useState(() => readUser() === null);

  useEffect(() => {
    if (!restoring) return;
    let active = true;
    AuthService.refresh()
      .catch(() => undefined)
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, [restoring]);

  const login = useCallback(async (username: string, password: string) => {
    const response = await AuthService.login(username, password);
    writeSession(response.access_token, response.user);
  }, []);

  const changePassword = useCallback(async (username: string, currentPassword: string, newPassword: string) => {
    const response = await AuthService.changePassword(username, currentPassword, newPassword);
    writeSession(response.access_token, response.user);
  }, []);

  const logout = useCallback(async () => {
    // Close the refresh session on the server first; a failed call still ends the local session.
    await AuthService.logout().catch(() => undefined);
    clearAuth();
  }, []);

  const hasPermission = useCallback(
    (permission: string) =>
      Boolean(user?.is_super_admin || user?.permissions?.includes('*:*') || user?.permissions?.includes(permission)),
    [user],
  );

  const access = useMemo(() => accessOf(user), [user]);

  const value = useMemo(
    () => ({user, loading: restoring, access, login, changePassword, logout, hasPermission}),
    [user, restoring, access, login, changePassword, logout, hasPermission],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(Context);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
