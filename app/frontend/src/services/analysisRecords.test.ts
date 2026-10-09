import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth} from '@/lib/authStorage';
import {signedIn} from '@/test/render';
import {AnalysisRecordsService} from './analysisRecords';

const UNTIL = '2026-10-08T12:00:00Z';
const ASKER = '00000000-0000-4000-8000-0000000000b1';

describe('analysis record requests (analysis-records API sözleşmesi)', () => {
  let fetch: ReturnType<typeof vi.fn>;
  const sent = () => {
    const [url, init] = fetch.mock.calls.at(-1) as [string, RequestInit];
    const parsed = new URL(url, 'http://app.test');
    return {path: parsed.pathname.replace(/^.*\/v1/, ''), params: Object.fromEntries(parsed.searchParams), method: init.method ?? 'GET'};
  };

  beforeEach(() => {
    // The shared test setup answers these reads for the pages; here the real requests are wanted.
    vi.restoreAllMocks();
    signedIn('manager');
    fetch = vi.fn(async () => new Response('{}', {status: 200, headers: {'Content-Type': 'application/json'}}));
    vi.stubGlobal('fetch', fetch);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    clearAuth();
  });

  it('sends the filters, the page, its size and until with the list, and leaves empty filters out', async () => {
    await AnalysisRecordsService.list({period: '30d', flow: 'reused', asked_by: ASKER, q: 'işlem %'}, 2, UNTIL);
    expect(sent()).toEqual({
      path: '/analysis-records',
      params: {period: '30d', flow: 'reused', asked_by: ASKER, q: 'işlem %', until: UNTIL, page: '2', page_size: '150'},
      method: 'GET',
    });
    await AnalysisRecordsService.list({period: '7d', flow: '', asked_by: '', q: ''}, 1);
    expect(sent().params).toEqual({period: '7d', page: '1', page_size: '150'});
  });

  it('reads the summary, the daily counts, the askers and one record', async () => {
    await AnalysisRecordsService.summary({period: 'today', q: 'mevduat'}, UNTIL);
    expect(sent()).toMatchObject({path: '/analysis-records/summary', params: {period: 'today', q: 'mevduat', until: UNTIL}});
    await AnalysisRecordsService.dailyCounts(14);
    expect(sent()).toMatchObject({path: '/analysis-records/daily-counts', params: {days: '14'}});
    await AnalysisRecordsService.askers();
    expect(sent().path).toBe('/analysis-records/askers');
    await AnalysisRecordsService.detail('0b6f6f3e-3e0a-4c58-9a3a-8a2f9c1e2d11');
    expect(sent().path).toBe('/analysis-records/0b6f6f3e-3e0a-4c58-9a3a-8a2f9c1e2d11');
  });

  it('deletes everything before until, or the filter\'s records before until', async () => {
    await AnalysisRecordsService.remove(UNTIL, {all: true});
    expect(sent()).toEqual({path: '/analysis-records', params: {until: UNTIL, all: 'true'}, method: 'DELETE'});
    await AnalysisRecordsService.remove(UNTIL, {filters: {period: '7d', flow: 'failed', asked_by: '', q: ''}});
    expect(sent()).toEqual({path: '/analysis-records', params: {period: '7d', flow: 'failed', until: UNTIL}, method: 'DELETE'});
  });
});
