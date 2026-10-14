import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError, apiFetch, apiRequest, isUnreachable, refreshSession, visitorFetch, visitorRequest} from './apiClient';
import {clearAuth, readAccessToken, writeSession} from './authStorage';
import {deviceId} from './deviceId';
import type {AuthenticatedUser} from '@/types/auth';

const user = {username: 'ad.soyad', tenant_id: 'tenant-1'} as AuthenticatedUser;
const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json', ...headers}});
const expired = () => json(401, {detail: {code: 'not_authenticated', message: 'x'}}, {'WWW-Authenticate': 'Bearer'});
const issued = (token: string) => json(200, {access_token: token, token_type: 'bearer', expires_in: 900, user});

function requestOf(call: unknown[]): {url: string; headers: Headers; init: RequestInit} {
  const [url, init = {}] = call as [string, RequestInit | undefined];
  return {url, headers: new Headers(init.headers), init};
}

describe('shared API client', () => {
  beforeEach(() => writeSession('old', user));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    clearAuth();
  });

  it('sends a main-screen request with the device id only: no token, no tenant (003 Requirement 2)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, {ok: true}));
    await visitorRequest('/status');
    const {url, headers} = requestOf(fetchMock.mock.calls[0]);
    expect(url).toBe('/api/dwhnavigator/v1/status');
    expect(headers.get('X-Device-Id')).toBe(deviceId());
    expect(headers.has('Authorization')).toBe(false);
    expect(headers.has('x-tenant-id')).toBe(false);
    expect(url).not.toContain(deviceId());
  });

  it('keeps the session when a main-screen request is refused', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(expired());
    await expect(visitorFetch('/status')).rejects.toMatchObject({status: 401, sessionExpired: false});
    expect(readAccessToken()).toBe('old');
  });

  it('sends the bearer token and the tenant in headers, never in the address', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(200, {ok: true}));
    await apiRequest('/auth/me');
    const {url, headers} = requestOf(fetchMock.mock.calls[0]);
    expect(url).toBe('/api/dwhnavigator/v1/auth/me');
    expect(headers.get('Authorization')).toBe('Bearer old');
    expect(headers.get('x-tenant-id')).toBe('tenant-1');
    expect(url).not.toContain('old');
  });

  it('renews an expired token silently and repeats the request once', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(expired())
      .mockResolvedValueOnce(issued('new'))
      .mockResolvedValueOnce(json(200, {ok: true}));
    await expect(apiRequest('/explorer/galaxy')).resolves.toEqual({ok: true});
    const refresh = requestOf(fetchMock.mock.calls[1]);
    expect(refresh.url).toBe('/api/dwhnavigator/v1/auth/refresh');
    expect(refresh.init.method).toBe('POST');
    expect(refresh.init.credentials).toBe('same-origin');
    expect(refresh.headers.get('Authorization')).toBeNull();
    expect(requestOf(fetchMock.mock.calls[2]).headers.get('Authorization')).toBe('Bearer new');
    expect(readAccessToken()).toBe('new');
  });

  it('ends the session when the refresh is refused', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(expired())
      .mockResolvedValueOnce(json(401, {detail: {code: 'session_expired', message: 'x'}}));
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({status: 401, sessionExpired: true});
    expect(readAccessToken()).toBeNull();
  });

  it('shares one refresh between parallel requests and queues it behind a Web Lock', async () => {
    const lock = vi.fn((_name: string, run: () => Promise<unknown>) => run());
    vi.stubGlobal('navigator', {...navigator, locks: {request: lock}});
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) return issued('new');
      return new Headers(init?.headers).get('Authorization') === 'Bearer new' ? json(200, {ok: url}) : expired();
    });
    await Promise.all([apiRequest('/a'), apiRequest('/b'), apiRequest('/c')]);
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))).toHaveLength(1);
    expect(lock).toHaveBeenCalledTimes(1);
    expect(lock.mock.calls[0][0]).toBe('dwhnavigator-session-refresh');
  });

  it.each([
    ['a 401 without a challenge', () => json(401, {})],
    ['a proxy Basic challenge', () => json(401, {}, {'WWW-Authenticate': 'Basic realm="proxy"'})],
    ['a 403', () => json(403, {detail: {code: 'forbidden', message: 'x'}})],
    ['a 500', () => json(500, {detail: {code: 'internal_error', message: 'x'}})],
    ['a 502 from a proxy', () => new Response('<html>Bad Gateway</html>', {status: 502})],
  ])('keeps the session on %s', async (_, response) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response());
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({sessionExpired: false});
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(readAccessToken()).toBe('old');
  });

  it('keeps the session on a network error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(apiRequest('/auth/me')).rejects.toBeInstanceOf(TypeError);
    expect(readAccessToken()).toBe('old');
  });

  it('does not refresh for a request sent without a token, such as the sign-in', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(json(401, {detail: {code: 'invalid_credentials', message: 'x'}}, {'WWW-Authenticate': 'Bearer'}));
    await expect(apiRequest('/auth/login', {method: 'POST', body: '{}'}, false)).rejects.toMatchObject({
      code: 'invalid_credentials',
      sessionExpired: false,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBeNull();
  });

  it('reads the error envelope and the Retry-After header', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(429, {detail: {code: 'rate_limited', message: 'Çok fazla'}}, {'Retry-After': '120'}),
    );
    const error = (await apiFetch('/auth/login', {method: 'POST'}, false).catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({status: 429, code: 'rate_limited', message: 'Çok fazla', retryAfter: 120});
  });

  it('restores a session from the refresh cookie', async () => {
    clearAuth();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(issued('restored'));
    await refreshSession();
    expect(readAccessToken()).toBe('restored');
  });

  it('tells an unreachable server from an application answer', () => {
    expect(isUnreachable(new TypeError('Failed to fetch'))).toBe(true);
    expect(isUnreachable(new ApiError(502, 'Bad Gateway'))).toBe(true);
    expect(isUnreachable(new ApiError(503, 'x', 'search_index_not_ready'))).toBe(false);
    expect(isUnreachable(new ApiError(404, 'x', 'not_found'))).toBe(false);
  });
});
