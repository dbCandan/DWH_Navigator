import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {AnalysisService} from '@/services/analyses';
import {ExplorerService} from '@/services/explorer';
import {answer, answerObject, GALAXY, job, serveEvents, serviceStatus, tally} from '@/test/explorer';
import {message, renderApp, signedIn} from '@/test/render';
import {clearAuth} from '@/lib/authStorage';
import {RADAR_MS} from '@/lib/cosmos/engine';
import explorerCss from '@/components/explorer/explorer.css?raw';

/** A 2D context that draws nothing, so the map runs in the test (drawing is not tested here). */
function drawNothing() {
  const ctx = new Proxy({} as Record<string, unknown>, {
    get: (target, name) => {
      if (name in target) return target[name as string];
      if (name === 'measureText') return () => ({width: 40});
      if (name === 'createRadialGradient' || name === 'createConicGradient') return () => ({addColorStop: () => undefined});
      return () => undefined;
    },
    set: (target, name, value) => {
      target[name as string] = value;
      return true;
    },
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', () => undefined);
}

async function openExplorer() {
  signedIn('user', 'Ayşe Yılmaz');
  renderApp('/');
  await screen.findByRole('banner');
}

const field = () => screen.getByRole('textbox', {name: message('explorer.search.label')});
const hudCount = () => document.getElementById('hud-count');

describe('map data and table file on the main screen (dictionary-explorer Requirement 3, 9, 14, 16, 19)', () => {
  beforeEach(drawNothing);
  afterEach(() => {
    // Unmount while the stubs still stand: the map stops its frame loop on the way out.
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    clearAuth();
    document.documentElement.className = '';
  });

  it('draws the galaxy endpoint\'s tables and clusters', async () => {
    await openExplorer();
    await waitFor(() => expect(hudCount()).toHaveTextContent(message('explorer.hud.count', {tables: 7, clusters: 3})));
    expect(ExplorerService.galaxy).toHaveBeenCalledTimes(1);
  });

  it('works without the map while the index is not ready and tries again at the next status poll', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    vi.mocked(ExplorerService.galaxy).mockRejectedValueOnce(new ApiError(503, 'hazırlanıyor', 'search_index_not_ready'));
    // Every poll answers with a new object, as the network does.
    vi.mocked(AnalysisService.status).mockImplementation(async () => serviceStatus());
    await openExplorer();
    await waitFor(() => expect(ExplorerService.galaxy).toHaveBeenCalledTimes(1));
    expect(hudCount()).toBeEmptyDOMElement();
    await act(async () => vi.advanceTimersByTime(60000));
    await waitFor(() => expect(hudCount()).toHaveTextContent(message('explorer.hud.count', {tables: 7, clusters: 3})));
    expect(ExplorerService.galaxy).toHaveBeenCalledTimes(2);
  });

  it('reads the galaxy again when the status names another dictionary version, the open file staying open', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    await openExplorer();
    await waitFor(() => expect(hudCount()).toHaveTextContent(/7/));
    fireEvent.change(field(), {target: {value: 'vCustomerInfo'}});
    fireEvent.keyDown(field(), {key: 'Enter'});
    expect(document.getElementById('dossier')).toHaveClass('on');
    // The same version at the next poll: nothing is read; a new one: the map is built again.
    await act(async () => vi.advanceTimersByTime(60000));
    expect(ExplorerService.galaxy).toHaveBeenCalledTimes(1);
    vi.mocked(AnalysisService.status).mockResolvedValue(serviceStatus({dictionary_version: 'fedcba98-11200'}));
    vi.mocked(ExplorerService.galaxy).mockResolvedValue({items: [...GALAXY, {...GALAXY[0], key: 'DWH.Kart.vYeni', name: 'vYeni'}], total: 8});
    await act(async () => vi.advanceTimersByTime(60000));
    await waitFor(() => expect(hudCount()).toHaveTextContent(message('explorer.hud.count', {tables: 8, clusters: 3})));
    expect(document.getElementById('dossier')).toHaveClass('on');
  });

  it('opens a typed table name as its file without asking; Esc brings the focus back to the bar', async () => {
    const start = vi.spyOn(AnalysisService, 'start');
    await openExplorer();
    await waitFor(() => expect(hudCount()).toHaveTextContent(/7/));
    for (const typed of ['vcustomerınfo', 'Musteri.vCustomerInfo', 'DWH.Musteri.VCUSTOMERINFO']) {
      field().focus();
      fireEvent.change(field(), {target: {value: typed}});
      fireEvent.keyDown(field(), {key: 'Enter'});
      expect(document.getElementById('dossier')).toHaveClass('on');
      expect(ExplorerService.table).toHaveBeenLastCalledWith('DWH.Musteri.vCustomerInfo');
      fireEvent.keyDown(document, {key: 'Escape'});
      expect(document.getElementById('dossier')).not.toHaveClass('on');
      expect(document.activeElement).toBe(field());
      expect(field()).toHaveValue(typed);
    }
    expect(start).not.toHaveBeenCalled();
  });

  it('asks a name that is in two schemas as a question', async () => {
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await waitFor(() => expect(hudCount()).toHaveTextContent(/7/));
    fireEvent.change(field(), {target: {value: 'vCampaign'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(start).toHaveBeenCalledWith('vCampaign', false);
    expect(document.getElementById('dossier')).not.toHaveClass('on');
  });

  it('opens the file from "Kolonlar", from a table named in the prose and from an approved table; focus returns', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({
      ...job({state: 'completed'}),
      result: answer({
        objects: [answerObject(1, {reason: 'DWH.Musteri.vCustomerInfo ile birleşir.'})],
        endorsed: [{key: 'DWH.Kart.vCardStatistic', name: 'vCardStatistic', schema: 'DWH.Kart', votes: tally({up: 2, status: 'approved'})}],
        rejected: [],
      }),
    });
    await openExplorer();
    await waitFor(() => expect(hudCount()).toHaveTextContent(/7/));
    fireEvent.change(field(), {target: {value: 'kart limit doluluk oranı'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    // The answer waits for the radar's turn (Requirement 7, Decision 12).
    await act(async () => vi.advanceTimersByTime(RADAR_MS + 100));
    await screen.findByText(message('answer.verdict.partial'));
    fireEvent.click(document.querySelector('.pick-row') as HTMLElement);
    const columns = screen.getByRole('button', {name: message('answer.columns')});
    columns.focus();
    fireEvent.click(columns);
    expect(ExplorerService.table).toHaveBeenLastCalledWith('DWH.Kart.vCardLimit1');
    fireEvent.keyDown(document, {key: 'Escape'});
    expect(document.activeElement).toBe(columns);
    const prose = screen.getByTitle(message('answer.openDictionary', {key: 'DWH.Musteri.vCustomerInfo'}));
    fireEvent.click(prose);
    expect(ExplorerService.table).toHaveBeenLastCalledWith('DWH.Musteri.vCustomerInfo');
    fireEvent.keyDown(document, {key: 'Escape'});
    fireEvent.click(document.querySelector('button.crowd-item') as HTMLElement);
    expect(ExplorerService.table).toHaveBeenLastCalledWith('DWH.Kart.vCardStatistic');
    expect(document.getElementById('dossier')).toHaveClass('on');
  });
});

describe('the main screen moves whatever the system\'s "reduce motion" says (dictionary-explorer Requirement 8, Decision 8)', () => {
  let frames: FrameRequestCallback[];
  beforeEach(() => {
    drawNothing();
    frames = [];
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
    const media = window.matchMedia;
    vi.stubGlobal('matchMedia', (query: string) => ({...media(query), matches: query.includes('reduce')}));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    clearAuth();
    document.documentElement.className = '';
  });

  /** Run the map's frames for `ms` of page time, one frame every 40 ms. */
  const fly = async (ms: number) => {
    for (let spent = 0; spent < ms; spent += 40) {
      await act(async () => vi.advanceTimersByTime(40));
      const due = frames.splice(0);
      for (const frame of due) frame(performance.now());
    }
  };
  const voyageLog = () => document.getElementById('hud-focus')?.textContent ?? '';

  it('keeps the frame loop, marks the found tables on the radar and reads the final ones', async () => {
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date', 'performance'],
    });
    const [a, b, c] = GALAXY.map((t) => t.key);
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents(
      {type: 'tables', stage: 'prefilter', tables: [{key: a, source: 'engine', read: false}, {key: c, source: 'engine', read: false}]},
      {type: 'tables', stage: 'reading', tables: [{key: a, source: 'model', read: true}, {key: b, source: 'family', read: true}]},
      {type: 'completed', flow: 'analyst', verdict: 'VAR'},
    );
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await fly(200);
    await waitFor(() => expect(hudCount()).toHaveTextContent(/7/));
    await fly(200);
    expect(frames.length).toBe(1); // the map keeps asking for its next frame

    fireEvent.change(field(), {target: {value: 'kart limit doluluk oranı'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    await fly(RADAR_MS / 2);
    expect(screen.queryByText(message('answer.verdict.partial'))).toBeNull(); // still on the radar's turn
    expect(document.documentElement).toHaveClass('busy');
    await fly(RADAR_MS / 2 + 400);
    expect(voyageLog()).toContain(message('explorer.voyage.toRead', {count: 2, marks: 3}));
    await screen.findByText(message('answer.verdict.partial'));
    expect(frames.length).toBe(1);
  });

  it('glides the question bar up into the top line', async () => {
    const animate = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'animate', {value: animate, configurable: true, writable: true});
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      {left: 10, top: 300, width: 600, height: 80, right: 610, bottom: 380, x: 10, y: 300, toJSON: () => ({})} as DOMRect,
    );
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    try {
      await openExplorer();
      fireEvent.change(field(), {target: {value: 'kart limit doluluk oranı'}});
      await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
      await waitFor(() => expect(animate).toHaveBeenCalled());
    } finally {
      delete (HTMLElement.prototype as {animate?: unknown}).animate;
    }
  });

  it('carries no "reduce motion" rule in the main screen\'s stylesheet', () => {
    expect(explorerCss).not.toMatch(/prefers-reduced-motion/);
  });
});
