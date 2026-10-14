import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, writeSession} from '@/lib/authStorage';
import {deviceId} from '@/lib/deviceId';
import {AnalysisService} from '@/services/analyses';
import {ExplorerService} from '@/services/explorer';
import {TermListService} from '@/services/termLists';
import {VoteService} from '@/services/votes';
import type {AuthenticatedUser} from '@/types/auth';

const ok = (body: unknown = {}) =>
  new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}});

/** Every main-screen call goes as the visitor: the device id, no token and no tenant, even while an
 * administration session is open in the tab (application-foundation 003-anonymous-visitor
 * Requirement 2, 3, Decision 3). */
describe('main-screen services', () => {
  beforeEach(() => {
    vi.restoreAllMocks(); // the shared setup answers these services; here the real calls are read
    writeSession('yonetim-belirteci', {tenant_id: 'tenant-1'} as AuthenticatedUser);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it.each([
    ['status', () => AnalysisService.status()],
    ['start', () => AnalysisService.start('kart', false)],
    ['read', () => AnalysisService.get('id-1')],
    ['cancel', () => AnalysisService.cancel('id-1')],
    ['galaxy', () => ExplorerService.galaxy()],
    ['search', () => ExplorerService.search('kart')],
    ['table', () => ExplorerService.table('A.B.C')],
    ['vote', () => VoteService.cast({query: 'kart', scope: 'answer', vote: 'up'} as never)],
    ['newest list', () => TermListService.newest()],
  ])('%s', async (_name, call) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok());
    await call();
    const headers = new Headers((fetchMock.mock.calls[0][1] ?? {}).headers);
    expect(headers.get('X-Device-Id')).toBe(deviceId());
    expect(headers.has('Authorization')).toBe(false);
    expect(headers.has('x-tenant-id')).toBe(false);
  });

  it('follows the live events and downloads a report as the visitor', async () => {
    const stream = new Response('id: 1\ndata: {"type":"completed"}\n\n', {
      status: 200,
      headers: {'Content-Type': 'text/event-stream'},
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(stream);
    await AnalysisService.follow('id-1', () => true, new AbortController().signal);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    vi.spyOn(URL, 'revokeObjectURL').mockReturnValue(undefined);
    fetchMock.mockResolvedValueOnce(new Response(new Blob(['x']), {status: 200}));
    await AnalysisService.report('id-1');
    for (const [, init] of fetchMock.mock.calls) {
      const headers = new Headers((init ?? {}).headers);
      expect(headers.get('X-Device-Id')).toBe(deviceId());
      expect(headers.has('Authorization')).toBe(false);
    }
  });
});
