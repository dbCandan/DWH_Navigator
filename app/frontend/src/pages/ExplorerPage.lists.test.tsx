import {act, fireEvent, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {AnalysisService} from '@/services/analyses';
import {TermListService} from '@/services/termLists';
import {answer, job, LIST_ID, serveEvents, termList, termRow} from '@/test/explorer';
import {message, renderApp, signedIn} from '@/test/render';

async function openExplorer() {
  signedIn('user', 'Ayşe Yılmaz');
  renderApp('/');
  await screen.findByRole('banner');
}

const workbook = (name = 'terimler.xlsx') => new File(['xlsx'], name, {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
const picker = () => document.getElementById('xl-file') as HTMLInputElement;
const field = () => screen.getByRole('textbox', {name: message('explorer.search.label')});
const pill = () => document.getElementById('listpill');

function choose(file: File) {
  Object.defineProperty(picker(), 'files', {value: [file], configurable: true});
  fireEvent.change(picker());
}

function filesEvent(type: string, file?: File) {
  const event = new Event(type, {bubbles: true, cancelable: true});
  Object.defineProperty(event, 'dataTransfer', {value: {types: ['Files'], files: file ? [file] : []}});
  return event;
}

describe('term list on the main screen (list-search Requirement 11, 15, 17)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    clearAuth();
    sessionStorage.removeItem('dwhnavigator.list');
    document.documentElement.className = '';
  });

  it('opens an .xlsx-only file picker from the Excel button', async () => {
    await openExplorer();
    const click = vi.spyOn(picker(), 'click').mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole('button', {name: message('explorer.list.attachLabel')}));
    expect(click).toHaveBeenCalled();
    expect(picker().accept).toBe('.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(picker()).toHaveAttribute('hidden');
  });

  it('says the file is read, then shows the list at the head of the page', async () => {
    let started: (list: ReturnType<typeof termList>) => void = () => undefined;
    const start = vi.spyOn(TermListService, 'start').mockImplementation(() => new Promise((resolve) => (started = resolve)));
    await openExplorer();
    fireEvent.change(field(), {target: {value: 'yazılmış soru'}});
    const file = workbook();
    await act(async () => choose(file));
    expect(start).toHaveBeenCalledWith(file);
    expect(screen.getByText(message('list.reading', {name: 'terimler.xlsx'}))).toHaveAttribute('role', 'status');
    expect(field()).toHaveValue('');
    expect(document.documentElement).toHaveClass('docked');
    await act(async () => started(termList({status: 'completed', done: 3, eta_ms: null})));
    expect(screen.getByRole('heading', {level: 2, name: 'terimler.xlsx'})).toBeInTheDocument();
    expect(document.documentElement).toHaveClass('has-results');
    expect(pill()).toBeNull();
  });

  it('explains a refused file', async () => {
    vi.spyOn(TermListService, 'start').mockRejectedValue(
      new ApiError(422, 'Dosya Excel (.xlsx) olarak okunamadı. Beklenen biçim: A sütununda…', 'term_list_not_xlsx'),
    );
    await openExplorer();
    await act(async () => choose(workbook('bos.xlsx')));
    const help = await screen.findByText(message('list.help.failed', {name: 'bos.xlsx'}).trim());
    expect(help.closest('.error')).toHaveTextContent('“bos.xlsx” yüklenemedi. Dosya Excel (.xlsx) olarak okunamadı.');
    expect(help.closest('section')).toHaveClass('xl-help');
  });

  it('lights the bar while a file is dragged and starts the list on drop', async () => {
    const start = vi.spyOn(TermListService, 'start').mockResolvedValue(termList({status: 'completed', eta_ms: null}));
    await openExplorer();
    act(() => {
      window.dispatchEvent(filesEvent('dragenter'));
    });
    expect(document.documentElement).toHaveClass('dropping');
    const over = filesEvent('dragover');
    window.dispatchEvent(over);
    expect(over.defaultPrevented).toBe(true);
    const file = workbook();
    await act(async () => {
      window.dispatchEvent(filesEvent('drop', file));
    });
    expect(document.documentElement).not.toHaveClass('dropping');
    expect(start).toHaveBeenCalledWith(file);
  });

  it('asks a running list every 1.5 seconds and stops when it ends', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    vi.spyOn(TermListService, 'start').mockResolvedValue(termList());
    const get = vi
      .spyOn(TermListService, 'get')
      .mockResolvedValueOnce(termList({done: 2, items: [termList().items[0], termRow(2, {state: 'answered', verdict: 'VAR', flow: 'analyst'}), termRow(3, {state: 'running'})]}))
      .mockResolvedValue(termList({status: 'completed', done: 3, eta_ms: null}));
    await openExplorer();
    await act(async () => choose(workbook()));
    expect(get).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTime(1500));
    expect(get).toHaveBeenCalledWith(LIST_ID);
    expect(document.querySelector('.list-head .sub')).toHaveTextContent(message('list.progress.running', {done: 2, total: 3}));
    await act(async () => vi.advanceTimersByTime(1500));
    expect(document.querySelector('.list-head .sub')).toHaveTextContent(/^Tamamlandı/);
    await act(async () => vi.advanceTimersByTime(6000));
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('shows the running list instead of uploading another one', async () => {
    const start = vi.spyOn(TermListService, 'start').mockResolvedValue(termList());
    vi.spyOn(TermListService, 'get').mockResolvedValue(termList());
    await openExplorer();
    await act(async () => choose(workbook()));
    expect(start).toHaveBeenCalledTimes(1);
    await act(async () => choose(workbook('ikinci.xlsx')));
    expect(start).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', {level: 2, name: 'terimler.xlsx'})).toBeInTheDocument();
  });

  it('opens empty in a fresh tab and reads no list on page open (Decision 15)', async () => {
    const get = vi.spyOn(TermListService, 'get');
    sessionStorage.removeItem('dwhnavigator.list');
    await openExplorer();
    expect(get).not.toHaveBeenCalled();
    expect(pill()).toBeNull();
  });

  it('recalls the tab\'s list from sessionStorage on reload and leads back to it with the pill', async () => {
    sessionStorage.setItem('dwhnavigator.list', LIST_ID);
    vi.spyOn(TermListService, 'get').mockResolvedValue(termList({status: 'completed', done: 3, eta_ms: null}));
    await openExplorer();
    const button = await screen.findByRole('button', {name: message('list.pillResult')});
    expect(button).toHaveAttribute('id', 'listpill');
    expect(button).toHaveClass('pill', 'listpill');
    expect(button).toHaveAttribute('title', message('list.pillTip'));
    expect(button.querySelector('.dot')).not.toHaveClass('on');
    expect(button.parentElement).toHaveClass('tools');
    fireEvent.click(button);
    expect(screen.getByRole('heading', {level: 2, name: 'terimler.xlsx'})).toBeInTheDocument();
    expect(pill()).toBeNull();
  });

  it('forgets the tab\'s list when the server no longer has it', async () => {
    sessionStorage.setItem('dwhnavigator.list', LIST_ID);
    vi.spyOn(TermListService, 'get').mockRejectedValue(new ApiError(404, 'bulunamadı', 'term_list_not_found'));
    await openExplorer();
    await waitFor(() => expect(sessionStorage.getItem('dwhnavigator.list')).toBeNull());
    expect(pill()).toBeNull();
  });

  it('writes the tab\'s list id to sessionStorage when one is uploaded', async () => {
    sessionStorage.removeItem('dwhnavigator.list');
    vi.spyOn(TermListService, 'start').mockResolvedValue(termList({status: 'completed', eta_ms: null}));
    await openExplorer();
    await act(async () => choose(workbook()));
    expect(sessionStorage.getItem('dwhnavigator.list')).toBe(LIST_ID);
  });

  it('gives the page to a question; the pill comes back with the answer and a running list\'s poll', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    vi.spyOn(TermListService, 'start').mockResolvedValue(termList({status: 'cancelled', eta_ms: null}));
    vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await act(async () => choose(workbook()));
    fireEvent.change(field(), {target: {value: 'kart limit doluluk oranı'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    expect(document.querySelector('section.list')).toBeNull();
    await screen.findByText(message('answer.verdict.partial'));
    expect(pill()).toHaveTextContent(message('list.pillResult'));
    // Back to the list, then a resumed (running) list: the pill counts while a question is shown.
    fireEvent.click(pill() as HTMLElement);
    const resumed = termList();
    vi.spyOn(TermListService, 'resume').mockResolvedValue(resumed);
    vi.spyOn(TermListService, 'get').mockResolvedValue(resumed);
    await act(async () => fireEvent.click(screen.getByRole('button', {name: message('list.resume')})));
    fireEvent.change(field(), {target: {value: 'ikinci soru'}});
    await act(async () => fireEvent.keyDown(field(), {key: 'Enter'}));
    await act(async () => vi.advanceTimersByTime(1500));
    await waitFor(() => expect(pill()).toHaveTextContent(message('list.pillRunning', {done: 1, total: 3})));
    expect(pill()?.querySelector('.dot')).toHaveClass('on');
  });

  it('asks a term again as a new single question from its answer', async () => {
    vi.spyOn(TermListService, 'start').mockResolvedValue(termList({status: 'completed', eta_ms: null}));
    vi.spyOn(TermListService, 'item').mockResolvedValue(
      answer({query: 'terim 1', reused: {at: '09.10.2026 08:00', query: 'terim 1', match: 'aynı soru'}}),
    );
    const start = vi.spyOn(AnalysisService, 'start').mockResolvedValue(job());
    serveEvents({type: 'completed', flow: 'analyst', verdict: 'VAR'});
    vi.spyOn(AnalysisService, 'get').mockResolvedValue({...job({state: 'completed'}), result: answer()});
    await openExplorer();
    await act(async () => choose(workbook()));
    fireEvent.click(document.querySelector('.li-row') as HTMLElement);
    const redo = await screen.findByRole('button', {name: message('answer.redo')});
    await act(async () => fireEvent.click(redo));
    expect(start).toHaveBeenCalledWith('terim 1', true);
    expect(field()).toHaveValue('terim 1');
  });
});
