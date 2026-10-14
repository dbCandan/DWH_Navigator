import {clearAuth, readAccessToken, readUser, writeSession} from '@/lib/authStorage';
import {config} from '@/lib/config';
import {deviceId} from '@/lib/deviceId';
import type {LoginResponse} from '@/types/auth';

const DEVICE_HEADER = 'X-Device-Id';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: string | undefined = undefined,
    /** True only when this response proved the app's own session expired or invalid. */
    public readonly sessionExpired = false,
    /** Seconds the server asked to wait (`Retry-After`), when it said so. */
    public readonly retryAfter: number | undefined = undefined,
  ) {
    super(message);
  }
}

/**
 * RFC 6750: a 401 whose `WWW-Authenticate` challenge names the `Bearer` scheme (without an error,
 * or with `error="invalid_token"`) rejects the bearer credential that was sent. Any other 401,
 * such as a proxy's `Basic` challenge or a bare 401, says nothing about the app session.
 */
function rejectsBearerCredential(response: Response): boolean {
  if (response.status !== 401) return false;
  const challenge = response.headers.get('WWW-Authenticate')?.trim();
  if (!challenge) return false;
  const match = /^(\S+)(?:\s+(.*))?$/.exec(challenge);
  if (match === null || match[1].toLowerCase() !== 'bearer') return false;
  const error = /(?:^|[\s,])error="?([^",\s]+)"?/i.exec(match[2] ?? '')?.[1];
  return error === undefined || error === 'invalid_token';
}

function retryAfterSeconds(response: Response): number | undefined {
  const value = response.headers.get('Retry-After');
  if (value === null || !/^\d+$/.test(value.trim())) return undefined;
  return Number(value.trim());
}

/** Read the single error envelope `{"detail":{"code","message"}}`; anything else has no code. */
async function toApiError(response: Response, sessionExpired: boolean): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as {detail?: unknown};
  const detail = body.detail;
  let code: string | undefined;
  let message = 'Request failed';
  if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)) {
    const envelope = detail as {code?: unknown; message?: unknown};
    if (typeof envelope.code === 'string') code = envelope.code;
    if (typeof envelope.message === 'string') message = envelope.message;
  }
  return new ApiError(response.status, message, code, sessionExpired, retryAfterSeconds(response));
}

let refreshInFlight: Promise<LoginResponse> | null = null;

async function requestRefresh(): Promise<LoginResponse> {
  // The refresh cookie is HttpOnly and scoped to the auth path; the browser attaches it and the
  // Origin header, which the backend compares with the application address (Requirement 13).
  const response = await fetch(config.apiPrefix + '/auth/refresh', {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!response.ok) {
    const sessionEnded = response.status === 401;
    if (sessionEnded) clearAuth();
    throw await toApiError(response, sessionEnded);
  }
  const issued = (await response.json()) as LoginResponse;
  writeSession(issued.access_token, issued.user);
  return issued;
}

/**
 * Rotate the refresh cookie once for every caller that asks at the same time (Requirement 7). A
 * second rotation with the same cookie would look like token reuse and close the whole session
 * family, so concurrent requests in this tab share one call and other tabs wait on a Web Lock.
 */
export function refreshSession(): Promise<LoginResponse> {
  if (refreshInFlight === null) {
    const locks = typeof navigator === 'undefined' ? undefined : navigator.locks;
    const run = locks ? locks.request('dwhnavigator-session-refresh', requestRefresh) : requestRefresh();
    refreshInFlight = run.finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function sessionEndedError(): ApiError {
  return new ApiError(401, 'Session ended', 'session_expired', true);
}

function send(path: string, init: RequestInit, token: string | null, authenticated: boolean) {
  const headers = new Headers(init.headers);
  if (typeof init.body === 'string' && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  if (authenticated) {
    if (token) headers.set('Authorization', 'Bearer ' + token);
    const tenantId = readUser()?.tenant_id;
    if (tenantId && !headers.has(config.tenantHeader)) headers.set(config.tenantHeader, tenantId);
  }
  return fetch(config.apiPrefix + path, {...init, headers});
}

/**
 * Send one request through the shared client and return the successful response untouched, so
 * callers can read JSON, a file (download.ts) or an event stream (eventStream.ts). The access
 * token always travels in the `Authorization` header, never in the address (Requirement 12).
 * When the backend rejects the app's own bearer token the client refreshes the session once and
 * repeats the request; only a failed refresh ends the session (rules/31). Network, proxy,
 * upstream and unrelated authorization failures keep it.
 */
export async function apiFetch(path: string, init: RequestInit = {}, authenticated = true): Promise<Response> {
  const token = authenticated ? readAccessToken() : null;
  const response = await send(path, init, token, authenticated);
  if (response.ok) return response;
  if (token === null || !rejectsBearerCredential(response)) throw await toApiError(response, false);

  const current = readAccessToken();
  if (current === null) throw sessionEndedError();
  if (current === token) {
    try {
      await refreshSession();
    } catch (error) {
      if (error instanceof ApiError && error.sessionExpired) throw error;
      throw await toApiError(response, false);
    }
  }
  const renewed = readAccessToken();
  if (renewed === null) throw sessionEndedError();
  const retried = await send(path, init, renewed, authenticated);
  if (retried.ok) return retried;
  if (rejectsBearerCredential(retried) && readAccessToken() === renewed) {
    clearAuth();
    throw await toApiError(retried, true);
  }
  throw await toApiError(retried, false);
}

/** JSON request through the shared client; a 204 answer resolves to `undefined`. */
export async function apiRequest<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const response = await apiFetch(path, init, authenticated);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * A main-screen request: the visitor of the browser's device id asks, with no token and no tenant
 * header even while an administration session is open (application-foundation
 * 003-anonymous-visitor Requirement 2, 3, Decision 3). A refusal never ends that session.
 */
export async function visitorFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (typeof init.body === 'string' && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  headers.set(DEVICE_HEADER, deviceId());
  const response = await fetch(config.apiPrefix + path, {...init, headers});
  if (response.ok) return response;
  throw await toApiError(response, false);
}

export async function visitorRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await visitorFetch(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** A lost connection, or a gateway answering without the application behind it. */
export function isUnreachable(error: unknown): boolean {
  if (error instanceof ApiError) return error.code === undefined && [502, 503, 504].includes(error.status);
  return error instanceof TypeError;
}
