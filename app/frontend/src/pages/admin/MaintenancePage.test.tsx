import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {DictionaryService} from '@/services/dictionary';
import {SavedAnswersService} from '@/services/savedAnswers';
import {SearchSettingsService} from '@/services/searchSettings';
import {answerConfirm, dictionaryState, indexState} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {SearchIndexState} from '@/types/search';

const card = () => document.getElementById('sec-index') as HTMLElement;

async function openPage(index: SearchIndexState = indexState()) {
  vi.mocked(SearchSettingsService.index).mockResolvedValue(index);
  renderApp('/admin/bakim');
  return screen.findByRole('heading', {level: 2, name: message('maintenance.index.title')});
}

describe('Bakım page (search-settings Requirement 14-16, 19)', () => {
  beforeEach(() => {
    signedIn('manager');
    vi.mocked(DictionaryService.state).mockResolvedValue(dictionaryState());
    vi.mocked(DictionaryService.tables).mockResolvedValue([]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows a current index, its dictionary and build time, and the cache settings with the kept answers', async () => {
    vi.mocked(SavedAnswersService.summary).mockResolvedValue({total: 1200, usable: 800, newest_at: '2026-10-08T09:00:00Z'});
    await openPage();
    expect(screen.getByText(message('admin.page.bakim.description'))).toBeInTheDocument();
    expect(within(document.querySelector('#p-bakim .ph') as HTMLElement).getByRole('link', {name: message('maintenance.toDictionary')})).toHaveAttribute('href', '/admin/sozluk');
    expect(within(card()).getByText(message('maintenance.index.ok'))).toHaveClass('pill', 'ok');
    expect(within(card()).getByText(message('maintenance.index.dictionaryValue', {columns: 130, version: 'abcdef12'}))).toBeInTheDocument();
    expect(within(card()).getByRole('button', {name: message('maintenance.index.rebuild')})).not.toHaveClass('primary');
    expect(screen.getByRole('heading', {level: 2, name: 'Önceki cevaplar'})).toBeInTheDocument();
    expect(await screen.findByText(message('maintenance.answers.keptValue', {total: '1.200', usable: 800}))).toBeInTheDocument();
    expect(screen.getByText(message('maintenance.answers.newest'))).toBeInTheDocument();
    expect(screen.getByRole('button', {name: message('maintenance.answers.clear')})).toBeEnabled();
    expect(screen.getByText(message('admin.sys.indexOk'))).toBeInTheDocument();
  });

  it('names a stale index, its differing inputs and a failed attempt, and badges Bakım', async () => {
    await openPage(
      indexState({state: 'stale', stale_inputs: ['dictionary', 'terms'], last_failure: {at: '2026-10-08T10:00:00Z', trigger: 'terms'}}),
    );
    expect(within(card()).getByText(message('maintenance.index.stale'))).toHaveClass('pill', 'warn');
    expect(within(card()).getByText(message('maintenance.index.mismatch', {inputs: 'sözlük, terim sözlüğü'}))).toHaveClass('msg', 'warn');
    expect(within(card()).getByText(/Son kurulum denemesi başarısız oldu/)).toHaveClass('msg', 'bad');
    expect(within(card()).getByRole('button', {name: message('maintenance.index.rebuild')})).toHaveClass('btn', 'primary');
    expect(document.querySelector('#nav-bakim .bdg')).toHaveTextContent('!');
    expect(document.querySelector('#nav-bakim .bdg')).toHaveAttribute('title', message('admin.badge.indexStale'));
    expect(screen.getByText(message('admin.sys.indexStale'))).toBeInTheDocument();
  });

  it('shows an empty index, no dictionary and the import link', async () => {
    vi.mocked(DictionaryService.state).mockResolvedValue({active: null, previous: null, index_dictionary_version: ''});
    await openPage(indexState({columns: 0, objects: 0, dictionary_version: '', built_at: null}));
    expect(within(card()).getByText(message('maintenance.index.empty'))).toBeInTheDocument();
    expect(within(card()).getByText(message('maintenance.index.dictionaryNone'))).toBeInTheDocument();
    expect(within(card()).getByText('—')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: message('maintenance.toDictionarySetup')})).toBeInTheDocument();
  });

  it('reads the index every 2 seconds while it builds', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    try {
      await openPage(indexState({state: 'building', running: {at: '2026-10-08T10:00:00Z', trigger: 'manual'}}));
      expect(within(card()).getByText(message('maintenance.index.building'))).toBeInTheDocument();
      expect(screen.getByText(message('admin.sys.indexBuilding'))).toBeInTheDocument();
      vi.mocked(SearchSettingsService.index).mockResolvedValue(indexState());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(within(card()).getByText(message('maintenance.index.ok'))).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('rebuilds the index on request and reports the result or the failure', async () => {
    const rebuild = vi
      .spyOn(SearchSettingsService, 'rebuild')
      .mockResolvedValueOnce({...indexState({columns: 1557, objects: 87}), elapsed_ms: 900})
      .mockRejectedValueOnce(new ApiError(503, 'x', 'search_change_busy'));
    await openPage();
    const button = within(card()).getByRole('button', {name: message('maintenance.index.rebuild')});
    fireEvent.click(button);
    expect(await screen.findByText(message('admin.index.rebuilt'))).toBeInTheDocument();
    expect(screen.getByText(/^1\.557 kolon · 87 tablo · \d+\.\d sn$/)).toBeInTheDocument();
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText(message('admin.index.failed'))).toBeInTheDocument();
    expect(screen.getByText(message('admin.error.search_change_busy'))).toBeInTheDocument();
    expect(rebuild).toHaveBeenCalledTimes(2);
  });

  it('deletes the kept answers after the browser confirmation', async () => {
    vi.mocked(SavedAnswersService.summary).mockResolvedValue({total: 12, usable: 3, newest_at: null});
    const clear = vi.spyOn(SavedAnswersService, 'clear').mockResolvedValue({removed: 12});
    const confirm = answerConfirm(false, true);
    await openPage();
    const button = await screen.findByRole('button', {name: message('maintenance.answers.clear')});
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(confirm).toHaveBeenCalledWith(message('maintenance.answers.confirm', {count: 12}));
    expect(clear).not.toHaveBeenCalled();
    vi.mocked(SavedAnswersService.summary).mockResolvedValue({total: 0, usable: 0, newest_at: null});
    fireEvent.click(button);
    expect(await screen.findByText(message('maintenance.answers.cleared'))).toBeInTheDocument();
    expect(screen.getByText(message('maintenance.answers.clearedLine', {count: 12}))).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(message('maintenance.answers.none'))).toBeInTheDocument());
    expect(button).toBeDisabled();
  });

  it('keeps "Önceki cevapları sil…" disabled when the summary cannot be read', async () => {
    vi.mocked(SavedAnswersService.summary).mockRejectedValue(new ApiError(404, 'Not Found'));
    await openPage();
    expect(screen.getByText(message('maintenance.answers.none'))).toBeInTheDocument();
    expect(screen.getByRole('button', {name: message('maintenance.answers.clear')})).toBeDisabled();
  });

  it('rebuilds the index from the command palette', async () => {
    const rebuild = vi.spyOn(SearchSettingsService, 'rebuild').mockResolvedValue({...indexState(), elapsed_ms: 10});
    await openPage();
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    fireEvent.change(await screen.findByRole('textbox', {name: message('admin.palette.label')}), {target: {value: 'indeksini'}});
    fireEvent.click(screen.getByText(message('admin.palette.rebuild'), {selector: '.pi div'}));
    expect(await screen.findByText(message('admin.index.rebuilt'))).toBeInTheDocument();
    expect(rebuild).toHaveBeenCalledTimes(1);
  });
});
