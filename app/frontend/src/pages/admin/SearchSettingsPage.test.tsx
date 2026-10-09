import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {SearchSettingsService} from '@/services/searchSettings';
import {answerConfirm, indexState, searchSettings} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';

const row = (key: string) => document.getElementById('row-' + key) as HTMLElement;
const bar = () => document.getElementById('savebar') as HTMLElement;

async function openPage(path = '/admin/arama') {
  renderApp(path);
  return screen.findByRole('heading', {level: 2, name: 'Analist'});
}

describe('Arama ve cevap page and the unsaved-changes bar (search-settings Requirement 17, 18, 23)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows the plain sections as cards and the expert ones folded with their counts', async () => {
    await openPage();
    expect(screen.getByText(message('admin.page.arama.description'))).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'Eş anlamlılar ve terimler'})).toBeInTheDocument();
    expect(screen.queryByRole('heading', {level: 2, name: 'Önceki cevaplar'})).toBeNull();
    expect(screen.getByText(message('settings.expertFold', {count: 1}))).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 3, name: message('settings.expert.title')})).toBeInTheDocument();
    expect(screen.getByText(message('settings.expert.note'))).toBeInTheDocument();
    const fold = screen.getByText('Kelime araması').closest('details') as HTMLElement;
    expect(within(fold).getByText(message('settings.expert.count', {count: 1}))).toHaveClass('tag');
    expect(row('search.bm25.k1').closest('details')).toBe(fold);
    expect(within(row('search.bm25.k1')).getByText(message('settings.reindex'))).toHaveAttribute('title', message('settings.reindexTip'));
    expect(within(row('analyst.shortlist')).getByText('Kolonları okunacak aday tablo sayısı')).toHaveAttribute('title', 'analyst.shortlist');
    expect(within(row('analyst.min_confidence')).getByText('%50')).toHaveClass('readout');
    expect(within(row('search.bm25.k1')).getByRole('spinbutton')).toHaveValue(1.2);
  });

  it('marks changed and non-default rows, returns to the default and counts the changes per page', async () => {
    await openPage();
    expect(bar()).not.toHaveClass('on');
    fireEvent.change(within(row('analyst.shortlist')).getByRole('spinbutton'), {target: {value: '20'}});
    expect(row('analyst.shortlist')).toHaveClass('row', 'changed', 'nondefault');
    expect(within(row('analyst.shortlist')).getByRole('slider')).toHaveValue('20');
    fireEvent.change(within(row('analyst.min_confidence')).getByRole('slider'), {target: {value: '0.75'}});
    expect(within(row('analyst.min_confidence')).getByText('%75')).toBeInTheDocument();
    expect(bar()).toHaveClass('savebar', 'on');
    expect(document.body).toHaveClass('unsaved');
    expect(within(bar()).getByText(message('admin.save.count', {count: 2}))).toBeInTheDocument();
    expect(within(bar()).getByText(message('admin.page.arama.label'))).toBeInTheDocument();
    expect(document.querySelector('#nav-arama .bdg')).toHaveTextContent('2');

    const reset = within(row('analyst.shortlist')).getByRole('button', {name: message('settings.reset')});
    expect(reset).toHaveAttribute('title', message('settings.resetTip', {value: '14'}));
    fireEvent.click(reset);
    expect(row('analyst.shortlist')).toHaveClass('row');
    expect(row('analyst.shortlist')).not.toHaveClass('changed');
    expect(within(row('analyst.shortlist')).getByRole('spinbutton')).toHaveValue(14);

    fireEvent.click(screen.getByRole('link', {name: message('admin.page.bakim.label')}));
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    fireEvent.click(within(document.getElementById('row-cache.enabled') as HTMLElement).getByRole('checkbox'));
    expect(within(bar()).getByText(message('admin.save.count', {count: 2}))).toBeInTheDocument();
    expect(within(bar()).getByText(`${message('admin.page.arama.label')} · ${message('admin.page.bakim.label')}`)).toBeInTheDocument();
    expect(document.querySelector('#nav-bakim .bdg')).toHaveTextContent('1');

    fireEvent.click(within(bar()).getByRole('button', {name: message('admin.save.revert')}));
    expect(bar()).not.toHaveClass('on');
    expect(document.body).not.toHaveClass('unsaved');
  });

  it('saves every change in one request and says when the word index was rebuilt', async () => {
    const save = vi.spyOn(SearchSettingsService, 'save').mockResolvedValue({
      changed: ['analyst.shortlist', 'search.bm25.k1'],
      values: searchSettings({'analyst.shortlist': 20, 'search.bm25.k1': 1.5}).values,
      elapsed_ms: 1800,
      index: indexState(),
    });
    await openPage();
    fireEvent.change(within(row('analyst.shortlist')).getByRole('spinbutton'), {target: {value: '20'}});
    fireEvent.change(within(row('search.bm25.k1')).getByRole('spinbutton'), {target: {value: '1.5'}});
    vi.mocked(SearchSettingsService.settings).mockResolvedValue(searchSettings({'analyst.shortlist': 20, 'search.bm25.k1': 1.5}));
    fireEvent.click(within(bar()).getByRole('button', {name: message('admin.save.apply')}));
    expect(await screen.findByText(message('admin.save.saved'))).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith({'analyst.shortlist': 20, 'search.bm25.k1': 1.5});
    expect(screen.getByText(message('admin.save.changed', {labels: 'Kolonları okunacak aday tablo sayısı, BM25 k1'}))).toBeInTheDocument();
    expect(screen.getByText(message('admin.save.reindexed', {duration: '1,8 sn'}))).toBeInTheDocument();
    await waitFor(() => expect(bar()).not.toHaveClass('on'));
    expect(row('analyst.shortlist')).toHaveClass('nondefault');
    expect(row('analyst.shortlist')).not.toHaveClass('changed');
  });

  it('keeps the draft and shows the server sentence when the values are refused', async () => {
    vi.spyOn(SearchSettingsService, 'save').mockRejectedValue(
      new ApiError(422, 'Kolonları okunacak aday tablo sayısı: 3 ile 30 arasında olmalı', 'search_setting_invalid'),
    );
    await openPage();
    fireEvent.change(within(row('analyst.shortlist')).getByRole('spinbutton'), {target: {value: '99'}});
    fireEvent.click(within(bar()).getByRole('button', {name: message('admin.save.apply')}));
    expect(await screen.findByText('Kolonları okunacak aday tablo sayısı: 3 ile 30 arasında olmalı')).toBeInTheDocument();
    expect(screen.getByText(message('admin.save.failed'))).toBeInTheDocument();
    expect(bar()).toHaveClass('on');
  });

  it('keeps unsaved values when new ones arrive from the server', async () => {
    await openPage();
    fireEvent.change(within(row('analyst.shortlist')).getByRole('spinbutton'), {target: {value: '20'}});
    vi.mocked(SearchSettingsService.settings).mockResolvedValue(searchSettings({'cache.max_age_days': 7}));
    fireEvent.click(screen.getByRole('link', {name: message('admin.page.bakim.label')}));
    await waitFor(() => expect(within(document.getElementById('row-cache.max_age_days') as HTMLElement).getByRole('spinbutton')).toHaveValue(7));
    fireEvent.click(document.getElementById('nav-arama') as HTMLElement);
    expect(await screen.findByRole('heading', {level: 2, name: 'Analist'})).toBeInTheDocument();
    expect(within(row('analyst.shortlist')).getByRole('spinbutton')).toHaveValue(20);
    expect(within(bar()).getByText(message('admin.save.count', {count: 1}))).toBeInTheDocument();
  });

  it('asks before leaving the admin screen with unsaved settings, not when moving between its pages', async () => {
    await openPage();
    fireEvent.change(within(row('analyst.shortlist')).getByRole('spinbutton'), {target: {value: '20'}});
    const confirm = answerConfirm(true);
    fireEvent.click(document.getElementById('nav-sozluk') as HTMLElement);
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('link', {name: message('admin.back')}));
    expect(confirm).toHaveBeenCalledWith(message('admin.leave.confirm'));
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/'));
  });

  it('goes to a setting from the command palette: opens its page and fold, flashes and focuses its row', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    try {
      renderApp('/admin/genel');
      await screen.findByRole('heading', {level: 1, name: message('admin.page.genel.label')});
      fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
      const box = await screen.findByRole('textbox', {name: message('admin.palette.label')});
      fireEvent.change(box, {target: {value: 'bm25'}});
      const option = screen.getByRole('option');
      expect(option).toHaveTextContent('BM25 k1');
      expect(option).toHaveTextContent(
        message('admin.palette.settingTipHelp', {page: message('admin.page.arama.label'), section: 'Kelime araması', help: 'Aynı kelimenin tekrarı ne kadar sayılsın.'}),
      );
      fireEvent.keyDown(box, {key: 'Enter'});
      await screen.findByRole('heading', {level: 2, name: 'Analist'});
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
      expect(row('search.bm25.k1')).toHaveClass('flash');
      expect((row('search.bm25.k1').closest('details') as HTMLDetailsElement).open).toBe(true);
      expect(document.activeElement).toBe(within(row('search.bm25.k1')).getByRole('slider'));
    } finally {
      vi.useRealTimers();
    }
  });
});
