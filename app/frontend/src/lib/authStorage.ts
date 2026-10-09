import type {AuthenticatedUser} from '@/types/auth';

/**
 * The only module that holds the session (user-accounts Requirement 6). The access token and the
 * user live in memory only: nothing is written to localStorage, sessionStorage or a readable
 * cookie. A page reload restores the session through the HttpOnly refresh cookie, which this
 * code never sees (Requirement 7).
 */
interface Session {
  accessToken: string;
  user: AuthenticatedUser;
}

let session: Session | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of [...listeners]) listener();
}

export function readAccessToken(): string | null {
  return session?.accessToken ?? null;
}

export function readUser(): AuthenticatedUser | null {
  return session?.user ?? null;
}

export function writeSession(accessToken: string, user: AuthenticatedUser): void {
  session = {accessToken, user};
  notify();
}

export function clearAuth(): void {
  if (session === null) return;
  session = null;
  notify();
}

/** Subscribe to session changes; returns the unsubscribe function. */
export function subscribeAuth(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
