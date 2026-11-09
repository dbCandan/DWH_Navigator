import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, readAccessToken} from '@/lib/authStorage';
import {ApiError} from '@/lib/apiClient';
import {recallTabAnalysis, rememberTabAnalysis} from '@/lib/tabAnalysis';
import {AnalysisService} from '@/services/analyses';
import {AuthService} from '@/services/auth';
import {ANALYSIS_ID, answer, job, serveEvents, serviceStatus} from '@/test/explorer';
import {message, renderApp, signedIn} from '@/test/render';

async function openExplorer(kind: 'user' | 'manager' | 'super' = 'user') {
  signedIn(kind, 'Ayşe Yılmaz');
  renderApp('/');
  return screen.findByRole('banner');
}

describe('main screen shell (dictionary-explorer Requirement 1, 15, 17)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
    sessionStorage.clear();
    document.documentElement.className = '';
  });

  it('shows the brand, the landing title and the question bar in the source\'s structure', async () => {
    await openExplorer();
    expect(document.documentElement.dataset.surface).toBe('explorer');
    await waitFor(() => expect(document.title).toBe(message('explorer.documentTitle')));
    const brand = screen.getByRole('link', {name: /DWH Navigator/});
    expect(brand).toHaveAttribute('href', '/');
    expect(brand).toHaveAttribute('title', message('explorer.brand.restart'));
    expect(brand).toHaveClass('brand');
    expect(screen.getByRole('heading', {level: 1, name: message('explorer.hero.title')})).toBeInTheDocument();
    const question = screen.getByRole('textbox', {name: message('explorer.search.label')});
    expect(question).toHaveAttribute('id', 'q');
    expect(question.closest('#hero > .searchbox')).not.toBeNull();
    expect(document.querySelector('header.top .wrap > #bar-slot.slot')).not.toBeNull();
    expect(document.querySelector('header.top .tools > #status.status')).not.toBeNull();
    // The map loads lazily (rules/30): it arrives after the page shell.
    await waitFor(() => expect(document.querySelector('#cosmos')).toHaveAttribute('aria-hidden', 'true'));
  });

  it.each(['user', 'manager', 'super'] as const)('offers no link to the admin screen (%s)', async (kind) => {
    await openExplorer(kind);
    for (const link of screen.getAllByRole('link')) expect(link.getAttribute('href')).not.toMatch(/admin/);
  });

  it('opens without signing in and shows no session area (003-anonymous-visitor Requirement 1, 8)', async () => {
    vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'x', 'session_expired', true));
    renderApp('/');
    expect(await screen.findByRole('heading', {level: 1, name: message('explorer.hero.title')})).toBeInTheDocument();
    expect(screen.getByTestId('where').textContent).toBe('/');
    expect(screen.queryByRole('button', {name: /Ayşe|session/i})).toBeNull();
    expect(screen.queryByRole('link', {name: message('session.changePassword')})).toBeNull();
    expect(readAccessToken()).toBeNull();
  });

  it('shows no session area even with an administration session open', async () => {
    await openExplorer('manager');
    expect(screen.queryByRole('button', {name: message('session.menu', {name: 'Ayşe Yılmaz'})})).toBeNull();
  });

  it('sends a signed-out visitor of /admin to the sign-in screen', async () => {
    vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'x', 'session_expired', true));
    renderApp('/admin');
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/login'));
  });

  it('starts over from the brand without leaving the page', async () => {
    await openExplorer();
    const question = screen.getByRole('textbox', {name: message('explorer.search.label')});
    fireEvent.change(question, {target: {value: 'kredi kartı limiti'}});
    fireEvent.click(screen.getByRole('link', {name: /DWH Navigator/}));
    expect(question).toHaveValue('');
    expect(screen.getByTestId('where').textContent).toBe('/');
  });

  it('puts the veil behind the top line and moves the HUD aside as the page scrolls', async () => {
    await openExplorer();
    const root = document.documentElement;
    Object.defineProperty(window, 'scrollY', {value: 200, configurable: true});
    await act(async () => window.dispatchEvent(new Event('scroll')));
    expect(root).toHaveClass('lifted');
    expect(root).toHaveClass('scrolled');
    Object.defineProperty(window, 'scrollY', {value: 0, configurable: true});
    await act(async () => window.dispatchEvent(new Event('scroll')));
    expect(root).not.toHaveClass('lifted');
  });

  it('keeps every control reachable from the keyboard', async () => {
    await openExplorer();
    const controls = [...document.querySelectorAll<HTMLElement>('a[href], button, textarea')];
    expect(controls.length).toBeGreaterThan(3);
    for (const control of controls) expect(control.tabIndex).toBeGreaterThanOrEqual(0);
  });
});

describe('status pill and warning line (dictionary-explorer Requirement 2)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
    sessionStorage.clear();
    document.documentElement.className = '';
  });

  it.each([
    [serviceStatus(), '', 'explorer.status.ready', ''],
    [serviceStatus({objects: 0, columns: 0}), 'warn', 'explorer.status.noDictionary', 'explorer.warn.noDictionary'],
    [
      serviceStatus({llm: '', llm_state: {state: 'none', model: '', code: null, reason: ''}}),
      'warn',
      'explorer.status.modelNone',
      'explorer.warn.modelNone',
    ],
  ])('shows the pill and the line for each state', async (status, tone, label, warn) => {
    vi.mocked(AnalysisService.status).mockResolvedValue(status);
    await openExplorer();
    const pill = await screen.findByText(message(label));
    expect(pill).toHaveClass('pill');
    if (tone) expect(pill).toHaveClass(tone);
    expect(pill.querySelector('.dot')).toHaveClass(...(tone ? ['dot'] : ['dot', 'on']));
    expect(document.getElementById('model-warn')).toHaveTextContent(warn ? message(warn) : '');
  });

  it('says the model cannot be reached with its reason, and the dictionary size in the tooltip', async () => {
    vi.mocked(AnalysisService.status).mockResolvedValue(
      serviceStatus({llm_state: {state: 'down', model: 'm', code: 'connection', reason: 'Model sunucusuna ulaşılamadı'}}),
    );
    await openExplorer();
    const pill = await screen.findByText(message('explorer.status.modelDown'));
    expect(pill).toHaveClass('pill', 'bad');
    expect(pill).toHaveAttribute('title', 'Sözlük: 11.136 kolon · 390 tablo\nModel: Model sunucusuna ulaşılamadı');
    expect(document.getElementById('model-warn')).toHaveClass('model-warn', 'bad');
    expect(document.getElementById('model-warn')).toHaveTextContent(
      message('explorer.warn.modelDown', {reason: 'Model sunucusuna ulaşılamadı.'}),
    );
  });

  it('says the server cannot be reached when the status request fails', async () => {
    vi.mocked(AnalysisService.status).mockRejectedValue(new TypeError('Failed to fetch'));
    await openExplorer();
    expect(await screen.findByText(message('explorer.status.unreachable'))).toHaveClass('pill');
  });
});

describe('question bar and answer (question-analysis Requirement 19-21)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
    sessionStorage.clear();
    document.documentElement.className = '';
  });

  const field = () => screen.getByRole('textbox', {name: message('explorer.search.label')});

  function answerAfter(...events: Parameters<typeof serveEvents>) {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents(...events);
    return vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
  }

  it('does not ask an empty question, keeps Shift+Enter as a new line and asks on Enter', async () => {
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    fireEvent.keyDown(field(), {key: 'Enter'});
    expect(start).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(field());
    fireEvent.change(field(), {target: {value: '  kart limit doluluk oranı  '}});
    fireEvent.keyDown(field(), {key: 'Enter', shiftKey: true});
    expect(start).not.toHaveBeenCalled();
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(start).toHaveBeenCalledWith('kart limit doluluk oranı', false);
    // The bar now heads the page in the top line, with the question as its tooltip.
    expect(document.documentElement).toHaveClass('docked');
    expect(field().closest('#bar-slot > .searchbox')).not.toBeNull();
    expect(field()).toHaveAttribute('title', 'kart limit doluluk oranı');
    expect(document.getElementById('hero')).toHaveClass('compact');
    await screen.findByText(message('answer.verdict.partial'));
    expect(document.documentElement).toHaveClass('has-results');
  });

  it('turns "Ara" into "Durdur" while the analysis runs; Esc stops it and says so', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'running', ahead: null}));
    const cancel = vi.spyOn(AnalysisService, 'cancel').mockResolvedValue(job({state: 'cancelled'}));
    vi.spyOn(AnalysisService, 'follow').mockImplementation(
      (_id, _onEvent, signal) => new Promise((resolve) => signal.addEventListener('abort', () => resolve('aborted'))),
    );
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'soru'}});
    await act(async () => fireEvent.click(screen.getByRole('button', {name: /Ara/})));
    const stop = await screen.findByRole('button', {name: message('explorer.search.stop')});
    expect(stop).toHaveClass('primary', 'busy');
    expect(stop).toHaveAttribute('title', message('explorer.search.stopTip'));
    expect(document.documentElement).toHaveClass('busy');
    await act(async () => fireEvent.keyDown(document, {key: 'Escape'}));
    expect(cancel).toHaveBeenCalledWith(ANALYSIS_ID);
    const stopped = await screen.findByText(message('explorer.ask.stopped'));
    expect(stopped).toHaveClass('stopped');
    expect(stopped).toHaveAttribute('role', 'status');
    expect(document.documentElement).not.toHaveClass('busy');
    expect(document.documentElement).toHaveClass('found');
  });

  it('writes the failure and the interruption texts', async () => {
    vi.spyOn(AnalysisService, 'start').mockRejectedValue(new ApiError(429, 'raw', 'rate_limited'));
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'soru'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(
      await screen.findByText(message('explorer.ask.failed', {message: message('explorer.ask.error.rate_limited')})),
    ).toHaveClass('error');
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'interrupted'});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(await screen.findByText(message('explorer.ask.interrupted'))).toHaveAttribute('role', 'status');
  });

  it('focuses the docked bar with "/" and leaves it with Esc', async () => {
    answerAfter({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'soru'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    await screen.findByText(message('answer.verdict.partial'));
    (document.activeElement as HTMLElement | null)?.blur();
    fireEvent.keyDown(document, {key: '/'});
    expect(document.activeElement).toBe(field());
    fireEvent.keyDown(document, {key: 'Escape'});
    expect(document.activeElement).not.toBe(field());
  });

  it('after a reload follows the question this tab started (Requirement 19, Decision 26)', async () => {
    rememberTabAnalysis(ANALYSIS_ID);
    const start = vi.spyOn(AnalysisService, 'start');
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get')
      .mockResolvedValueOnce({...job({state: 'running', ahead: null, query: 'süren soru'}), result: null})
      .mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await screen.findByText(message('answer.verdict.partial'));
    expect(AnalysisService.get).toHaveBeenNthCalledWith(1, ANALYSIS_ID);
    expect(field()).toHaveValue('süren soru');
    expect(field().closest('#bar-slot')).not.toBeNull();
    expect(start).not.toHaveBeenCalled();
  });

  it('opens a new tab empty while another tab\'s question runs, and asks its own (Decision 26)', async () => {
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await act(async () => undefined);
    expect(field()).toHaveValue('');
    expect(field().closest('#hero')).not.toBeNull();
    expect(AnalysisService.get).not.toHaveBeenCalled();
    fireEvent.change(field(), {target: {value: 'yeni sekmenin sorusu'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(start).toHaveBeenCalledWith('yeni sekmenin sorusu', false);
  });

  it.each([
    ['finished', () => Promise.resolve({...job({state: 'completed', query: 'biten soru'}), result: answer()})],
    ['gone', () => Promise.reject(new ApiError(404, 'Analiz bulunamadı.', 'analysis_not_found'))],
  ])('forgets the tab\'s question when it is %s and opens empty', async (_kind, read) => {
    rememberTabAnalysis(ANALYSIS_ID);
    vi.spyOn(AnalysisService, 'get').mockImplementation(read as never);
    await openExplorer();
    await waitFor(() => expect(recallTabAnalysis()).toBeNull());
    expect(field()).toHaveValue('');
    expect(field().closest('#hero')).not.toBeNull();
  });

  it('asks again with "fresh" from a kept answer and downloads the report through the shared client', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job({state: 'completed', flow: 'reused'}));
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({
      ...job({state: 'completed'}),
      result: answer({reused: {at: '08.10.2026 14:05', query: 'kart limit doluluk oranı', match: 'aynı soru'}}),
    });
    const report = vi.spyOn(AnalysisService, 'report').mockResolvedValue('VSA_ask_kart_20261009_0800.xlsx');
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'kart limit doluluk oranı'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    const redo = await screen.findByRole('button', {name: message('answer.redo')});
    fireEvent.click(screen.getByRole('link', {name: message('answer.report')}));
    expect(report).toHaveBeenCalledWith(ANALYSIS_ID);
    await act(async () => fireEvent.click(redo));
    expect(AnalysisService.start).toHaveBeenLastCalledWith('kart limit doluluk oranı', true);
  });

  it('reads the status again after an answer the analyst did not write', async () => {
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'unavailable', verdict: 'BULUNAMADI'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({
      ...job({state: 'completed', flow: 'unavailable'}),
      result: answer({analyst: false, objects: [], verdict: 'BULUNAMADI', fallback: 'Model sunucusuna ulaşılamadı.'}),
    });
    await openExplorer();
    await waitFor(() => expect(AnalysisService.status).toHaveBeenCalledTimes(1));
    fireEvent.change(field(), {target: {value: 'soru'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    await screen.findByText(message('answer.verdict.notFound'));
    expect(AnalysisService.status).toHaveBeenCalledTimes(2);
  });

  it('starts over from the brand after an answer: the bar comes back to the middle', async () => {
    answerAfter({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'soru'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    await screen.findByText(message('answer.verdict.partial'));
    fireEvent.click(screen.getByRole('link', {name: /DWH Navigator/}));
    expect(document.querySelector('.ans')).toBeNull();
    expect(document.documentElement).not.toHaveClass('docked');
    expect(document.documentElement).not.toHaveClass('has-results');
    expect(field().closest('#hero > .searchbox')).not.toBeNull();
    expect(field()).toHaveValue('');
  });
});
