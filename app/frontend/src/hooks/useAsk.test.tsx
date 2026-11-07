import {act, renderHook, waitFor} from '@testing-library/react';
import type {ReactNode} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {IntlProvider} from '@/contexts/IntlContext';
import {useAsk} from '@/hooks/useAsk';
import {ApiError} from '@/lib/apiClient';
import {recallTabAnalysis} from '@/lib/tabAnalysis';
import type {CosmosEngine} from '@/lib/cosmos/engine';
import {AnalysisService} from '@/services/analyses';
import {ExplorerService} from '@/services/explorer';
import {ANALYSIS_ID, answer, job, serveEvents, serviceStatus} from '@/test/explorer';
import {message} from '@/test/render';

function fakeEngine() {
  return {active: true, radarMs: 0, begin: vi.fn(), queued: vi.fn(), found: vi.fn(), focus: vi.fn(), end: vi.fn()};
}

function setup(engine = fakeEngine(), onUnavailable = vi.fn()) {
  const wrapper = ({children}: {children: ReactNode}) => <IntlProvider>{children}</IntlProvider>;
  const hook = renderHook(
    () =>
      useAsk({
        engine: () => engine as unknown as CosmosEngine,
        status: () => serviceStatus(),
        onUnavailable,
      }),
    {wrapper},
  );
  return {hook, engine, onUnavailable};
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return {promise, resolve};
}

describe('the question flow (question-analysis Requirement 19, 20)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts the job, follows it to the end and shows the answer at the end of the voyage', async () => {
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({ahead: 2}));
    const follow = serveEvents(
      {type: 'snapshot', analysis_id: ANALYSIS_ID, state: 'queued', ahead: 2, step: null, elapsed_ms: 10},
      {type: 'queued', ahead: 1},
      {type: 'started'},
      {type: 'step', key: 'shortlist', status: 'started', elapsed_ms: 900},
      {type: 'completed', flow: 'analyst', verdict: 'KISMEN VAR'},
    );
    const get = vi
      .spyOn(AnalysisService, 'get')
      .mockResolvedValue({...job({state: 'completed', flow: 'analyst'}), result: answer()});
    const {hook, engine, onUnavailable} = setup();
    await act(() => hook.result.current.ask('kart limit doluluk oranı', false));
    expect(start).toHaveBeenCalledWith('kart limit doluluk oranı', false);
    expect(follow).toHaveBeenCalledWith(ANALYSIS_ID, expect.any(Function), expect.any(AbortSignal));
    expect(get).toHaveBeenCalledWith(ANALYSIS_ID, expect.any(AbortSignal));
    expect(engine.begin).toHaveBeenCalledWith({columns: 11136});
    // "sırada" is written while analyses are ahead; steps and numbers are never shown.
    expect(engine.queued).toHaveBeenCalled();
    expect(engine.focus).toHaveBeenCalledWith(
      [
        {key: 'DWH.Kart.vCardLimit1', name: 'vCardLimit1', score: expect.any(Number)},
        {key: 'DWH.Kart.vCardLimit2', name: 'vCardLimit2', score: expect.any(Number)},
      ],
      'kart limit doluluk oranı',
    );
    expect(engine.end).toHaveBeenCalled();
    expect(onUnavailable).not.toHaveBeenCalled();
    expect(hook.result.current.running).toBe(false);
    expect(hook.result.current.outcome).toMatchObject({kind: 'answer', analysisId: ANALYSIS_ID});
  });

  it('marks the tables the analysis finds on the radar, from its own events', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    const prefilter = [{key: 'DWH.Kart.vCardLimit1', source: 'engine' as const, read: false}];
    const reading = [
      {key: 'DWH.Kart.vCardLimit1', source: 'model' as const, read: true},
      {key: 'DWH.Kart.vCardLimit2', source: 'family' as const, read: true},
      {key: 'DWH.Kart.vLimitAd', source: 'similar' as const, read: false},
    ];
    serveEvents(
      {type: 'tables', stage: 'prefilter', tables: prefilter},
      {type: 'tables', stage: 'reading', tables: reading},
      {type: 'completed', flow: 'analyst', verdict: 'VAR'},
    );
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    const search = vi.spyOn(ExplorerService, 'search');
    const {hook, engine} = setup();
    await act(() => hook.result.current.ask('kart limit doluluk oranı', false));
    expect(engine.found).toHaveBeenNthCalledWith(1, 'prefilter', prefilter);
    expect(engine.found).toHaveBeenNthCalledWith(2, 'reading', reading);
    expect(search).not.toHaveBeenCalled(); // no separate table search draws a guessed route
  });

  it('does not write "sırada" for a job that starts at once', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({ahead: 0}));
    serveEvents(
      {type: 'snapshot', analysis_id: ANALYSIS_ID, state: 'queued', ahead: 0, step: null, elapsed_ms: 1},
      {type: 'started'},
      {type: 'completed', flow: 'analyst', verdict: 'VAR'},
    );
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    const {hook, engine} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(engine.queued).not.toHaveBeenCalled();
  });

  it('shows a kept answer without following a stream and sends "fresh" for a new analysis', async () => {
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'completed', flow: 'reused'}));
    const follow = vi.spyOn(AnalysisService, 'follow');
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    const {hook} = setup();
    await act(() => hook.result.current.ask('soru', true));
    expect(start).toHaveBeenCalledWith('soru', true);
    expect(follow).not.toHaveBeenCalled();
    expect(hook.result.current.outcome?.kind).toBe('answer');
  });

  it('stops before the start answer arrives and then cancels the job at once', async () => {
    const started = deferred<ReturnType<typeof job>>();
    vi.spyOn(AnalysisService, 'start').mockReturnValue(started.promise);
    const cancel = vi.spyOn(AnalysisService, 'cancel').mockResolvedValue(job({state: 'cancelled'}));
    const follow = vi.spyOn(AnalysisService, 'follow');
    const {hook} = setup();
    let run!: Promise<void>;
    act(() => {
      run = hook.result.current.ask('soru', false);
    });
    expect(hook.result.current.running).toBe(true);
    act(() => hook.result.current.stop());
    await act(() => run);
    expect(hook.result.current.outcome).toEqual({kind: 'stopped'});
    expect(cancel).not.toHaveBeenCalled();
    await act(async () => started.resolve(job()));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith(ANALYSIS_ID));
    expect(follow).not.toHaveBeenCalled();
  });

  it('stops a running job: the stream ends and the job is cancelled', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'running', ahead: null}));
    const cancel = vi.spyOn(AnalysisService, 'cancel').mockResolvedValue(job({state: 'cancelled'}));
    vi.spyOn(AnalysisService, 'follow').mockImplementation(
      (_id, _onEvent, signal) =>
        new Promise((resolve) => signal.addEventListener('abort', () => resolve('aborted'), {once: true})),
    );
    const {hook} = setup();
    let run!: Promise<void>;
    act(() => {
      run = hook.result.current.ask('soru', false);
    });
    await waitFor(() => expect(AnalysisService.follow).toHaveBeenCalled());
    act(() => hook.result.current.stop());
    await act(() => run);
    expect(cancel).toHaveBeenCalledWith(ANALYSIS_ID);
    expect(hook.result.current.outcome).toEqual({kind: 'stopped'});
  });

  it.each([
    ['analysis_failed', message('explorer.ask.error.analysis_failed')],
    ['something_new', message('explorer.ask.error.unexpected')],
  ])('ends a failed job (%s) with its catalog text', async (code, text) => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'failed', code, message: 'sunucunun ham iletisi'});
    const {hook} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(hook.result.current.outcome).toEqual({kind: 'failed', message: text});
  });

  it('ends an interrupted job and a job cancelled elsewhere with their own states', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'interrupted'});
    const {hook} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(hook.result.current.outcome).toEqual({kind: 'interrupted'});
    serveEvents({type: 'cancelled'});
    await act(() => hook.result.current.ask('soru', false));
    expect(hook.result.current.outcome).toEqual({kind: 'stopped'});
  });

  it('maps a refused start to a Turkish text, never the server message', async () => {
    vi.spyOn(AnalysisService, 'start').mockRejectedValue(new ApiError(503, 'ham ileti', 'analysis_queue_full'));
    const {hook, engine} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(hook.result.current.outcome).toEqual({
      kind: 'failed',
      message: message('explorer.ask.error.analysis_queue_full'),
    });
    expect(engine.end).toHaveBeenCalled();
    vi.spyOn(AnalysisService, 'start').mockRejectedValue(new TypeError('Failed to fetch'));
    await act(() => hook.result.current.ask('soru', false));
    expect(hook.result.current.outcome).toEqual({kind: 'failed', message: message('explorer.ask.error.unreachable')});
  });

  it('reads the status again after an answer the analyst did not write', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'unavailable', verdict: 'BULUNAMADI'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({
      ...job({state: 'completed', flow: 'unavailable'}),
      result: answer({analyst: false, objects: [], verdict: 'BULUNAMADI', fallback: 'Model sunucusuna ulaşılamadı.'}),
    });
    const {hook, onUnavailable} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
  });

  it('follows the running job it is given without starting a new one', async () => {
    const start = vi.spyOn(AnalysisService, 'start');
    serveEvents(
      {type: 'snapshot', analysis_id: ANALYSIS_ID, state: 'running', ahead: null, step: 'analyst_report', elapsed_ms: 30000},
      {type: 'completed', flow: 'analyst', verdict: 'VAR'},
    );
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    const {hook} = setup();
    await act(() => hook.result.current.ask('soru', false, job({state: 'running', ahead: null})));
    expect(start).not.toHaveBeenCalled();
    expect(hook.result.current.outcome?.kind).toBe('answer');
  });
});

describe('the tab remembers its own question (question-analysis Requirement 19, Decision 26)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('remembers the running job for this tab and forgets it once the job ends', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    let remembered: string | null = null;
    vi.spyOn(AnalysisService, 'follow').mockImplementation(async (_id, onEvent) => {
      remembered = recallTabAnalysis();
      onEvent({id: '1', event: 'message', data: JSON.stringify({type: 'completed', flow: 'analyst', verdict: 'VAR'})});
      return 'completed';
    });
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    const {hook} = setup();
    await act(() => hook.result.current.ask('soru', false));
    expect(remembered).toBe(ANALYSIS_ID);
    expect(recallTabAnalysis()).toBeNull();
  });

  it('forgets the job when the person stops it', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'running', ahead: null}));
    vi.spyOn(AnalysisService, 'cancel').mockResolvedValue(job({state: 'cancelled'}));
    vi.spyOn(AnalysisService, 'follow').mockImplementation(
      (_id, _onEvent, signal) =>
        new Promise((resolve) => signal.addEventListener('abort', () => resolve('aborted'), {once: true})),
    );
    const {hook} = setup();
    let run!: Promise<void>;
    act(() => {
      run = hook.result.current.ask('soru', false);
    });
    await waitFor(() => expect(recallTabAnalysis()).toBe(ANALYSIS_ID));
    act(() => hook.result.current.stop());
    await act(() => run);
    expect(recallTabAnalysis()).toBeNull();
  });

  it('keeps the job when the page goes away while it runs: a reload follows it again', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'running', ahead: null}));
    vi.spyOn(AnalysisService, 'follow').mockImplementation(
      (_id, _onEvent, signal) =>
        new Promise((resolve) => signal.addEventListener('abort', () => resolve('aborted'), {once: true})),
    );
    const {hook} = setup();
    act(() => {
      void hook.result.current.ask('soru', false);
    });
    await waitFor(() => expect(recallTabAnalysis()).toBe(ANALYSIS_ID));
    hook.unmount();
    await act(async () => undefined);
    expect(recallTabAnalysis()).toBe(ANALYSIS_ID);
  });
});
