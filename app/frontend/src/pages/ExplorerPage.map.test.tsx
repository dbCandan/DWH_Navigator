import {act, cleanup, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {AnalysisService} from '@/services/analyses';
import {ExplorerService} from '@/services/explorer';
import {answer, answerObject, GALAXY, job, serveEvents, serviceStatus, tally} from '@/test/explorer';
import {message, renderApp, signedIn} from '@/test/render';
import {clearAuth} from '@/lib/authStorage';

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
    // Reduced motion: the answer does not wait for the radar's turn (Requirement 8).
    const media = window.matchMedia;
    vi.stubGlobal('matchMedia', (query: string) => ({...media(query), matches: query.includes('reduce')}));
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
