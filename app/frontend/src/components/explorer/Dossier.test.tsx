import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {useState} from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Dossier, type OpenTable} from '@/components/explorer/Dossier';
import {IntlProvider} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import {buildGalaxy} from '@/lib/cosmos/layout';
import {ExplorerService} from '@/services/explorer';
import {column, GALAXY, tableDetail} from '@/test/explorer';
import {message} from '@/test/render';
import type {TableDetail} from '@/types/explorer';

const galaxy = buildGalaxy(GALAXY);
const star = (key: string) => galaxy.byKey.get(key) ?? null;

/** The panel with an opener button outside it, as the page uses it. */
function Harness({first = 'DWH.Kart.vCardLimit1'}: {first?: string}) {
  const [table, setTable] = useState<OpenTable | null>(null);
  const [seq, setSeq] = useState(0);
  const open = (key: string) => {
    setSeq(seq + 1);
    setTable({key, star: star(key), seq: seq + 1});
  };
  return (
    <>
      <button type="button" onClick={() => open(first)}>
        aç
      </button>
      <Dossier table={table} onOpen={open} onClose={() => setTable(null)} />
    </>
  );
}

function show(first?: string) {
  render(
    <IntlProvider>
      <Harness first={first} />
    </IntlProvider>,
  );
  const opener = screen.getByRole('button', {name: 'aç'});
  opener.focus();
  fireEvent.click(opener);
  return opener;
}

const panel = () => document.getElementById('dossier') as HTMLElement;

describe('table file (dictionary-explorer Requirement 11-14)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.documentElement.className = '';
  });

  it('opens from the right with the cluster, the name, the key and the counts; zero is faint', async () => {
    show();
    expect(panel()).toHaveClass('on');
    expect(panel()).toHaveAttribute('role', 'dialog');
    // The dialog is named by the table's name (jsdom reads the <wbr> joints as spaces).
    expect(screen.getByRole('dialog')).toBe(panel());
    expect(panel()).toHaveAttribute('aria-labelledby', 'ds-name');
    expect(document.getElementById('ds-name')).toHaveTextContent('vCardLimit1');
    expect(document.documentElement).toHaveClass('dossier-open');
    expect(document.getElementById('ds-path')).toHaveTextContent('DWH.Kart.vCardLimit1');
    // Five placeholder rows until the columns arrive.
    expect(panel().querySelectorAll('.ds-skel')).toHaveLength(5);
    await screen.findByText('CardLimitAmount');
    expect(document.getElementById('ds-kicker')).toHaveTextContent('Kartlar');
    const stats = [...panel().querySelectorAll('.ds-stat')].map((s) => s.textContent);
    expect(stats).toEqual([
      '4' + message('dossier.statColumns'),
      '2' + message('dossier.statKeys'),
    ]);
    expect(panel().querySelector('.ds-stat.zero')).toBeNull();
    expect(panel().style.getPropertyValue('--hue')).toBe(String(star('DWH.Kart.vCardLimit1')?.hue));
  });

  it('writes the key badge and folds a long description; "Ek not yok" only when short', async () => {
    show();
    await screen.findByText('CardLimitAmount');
    const rows = [...panel().querySelectorAll('.ds-col')] as HTMLElement[];
    expect(rows[0]).toHaveClass('is-key');
    expect(within(rows[0]).getByText(message('dossier.keyBadge'))).toHaveAttribute('title', message('dossier.keyTip'));
    expect(within(rows[2]).getByText(message('dossier.noDescription'))).toHaveClass('ds-desc', 'none');
    expect(within(rows[0]).getByText(message('dossier.noNote'))).toBeInTheDocument();
    expect(within(rows[3]).queryByText(message('dossier.noNote'))).toBeNull();
    expect(within(rows[1]).getByText(message('dossier.synonyms'))).toBeInTheDocument();
  });

  it('opens a row with Enter and Space on its native button, and not while text is selected', async () => {
    show();
    await screen.findByText('CardLimitAmount');
    const row = panel().querySelectorAll('.ds-col')[1] as HTMLElement;
    const action = within(row).getByRole('button');
    expect(action).toHaveAttribute('aria-expanded', 'false');
    // A key press on a native button is a click with no pointer detail.
    fireEvent.click(action, {detail: 0});
    expect(row).toHaveClass('open');
    expect(action).toHaveAttribute('aria-expanded', 'true');
    vi.spyOn(window, 'getSelection').mockReturnValue({toString: () => 'İŞLEM'} as Selection);
    fireEvent.click(row, {detail: 1});
    expect(row).toHaveClass('open');
    fireEvent.click(action, {detail: 0});
    expect(row).not.toHaveClass('open');
  });

  it('searches names, descriptions and synonyms ignoring Turkish case and marks the hits', async () => {
    show();
    await screen.findByText('CardLimitAmount');
    const search = screen.getByRole('searchbox', {name: message('dossier.searchLabel')});
    expect(search).toHaveAttribute('placeholder', message('dossier.searchPlaceholder'));
    for (const text of ['İŞLEM', 'işlem', 'islem']) {
      fireEvent.change(search, {target: {value: text}});
      expect(panel().querySelectorAll('.ds-col')).toHaveLength(1);
      expect(document.getElementById('ds-count')).toHaveTextContent('1 / 4');
    }
    expect(panel().querySelector('.ds-col mark')).toHaveTextContent('İŞLEM');
    fireEvent.change(search, {target: {value: 'yok böyle'}});
    expect(screen.getByText(message('dossier.empty'))).toHaveClass('ds-empty');
  });

  it('filters by key; the chosen filter is pressed', async () => {
    vi.mocked(ExplorerService.table).mockResolvedValue(
      tableDetail({columns: [column('CustomerPartyId'), column('Amount')], join_keys: ['CustomerPartyId']}),
    );
    show();
    await screen.findByText('Amount');
    const all = screen.getByRole('button', {name: `${message('dossier.filterAll')} · 2`});
    const keys = screen.getByRole('button', {name: `${message('dossier.filterKey')} · 1`});
    expect(all).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(keys);
    expect(keys).toHaveAttribute('aria-pressed', 'true');
    expect(panel().querySelectorAll('.ds-col')).toHaveLength(1);
  });

  it('disables a filter without columns and dims its zero stat', async () => {
    vi.mocked(ExplorerService.table).mockResolvedValue(tableDetail({columns: [column('Amount')], join_keys: []}));
    show();
    await screen.findByText('Amount');
    expect(screen.getByRole('button', {name: `${message('dossier.filterKey')} · 0`})).toBeDisabled();
    expect(panel().querySelector('.ds-stat.key')).toHaveClass('zero');
  });

  it('lists at most 14 neighbours of the cluster by column count; another table replaces the file', async () => {
    show();
    await screen.findByText('CardLimitAmount');
    const foot = document.getElementById('ds-foot') as HTMLElement;
    expect(foot).not.toHaveClass('hidden');
    expect(foot.querySelector('.lbl')).toHaveTextContent(message('dossier.cluster', {count: 3}));
    const names = [...foot.querySelectorAll('.ds-sib')].map((b) => b.firstChild?.textContent);
    expect(names).toEqual(['vCardStatistic', 'vCardLimit2', 'vCampaign']);
    expect(foot.querySelector('.ds-sib')).toHaveAttribute(
      'title',
      message('explorer.star.columns', {schema: 'DWH.Kart', columns: 33}),
    );
    vi.mocked(ExplorerService.table).mockResolvedValue(tableDetail({key: 'DWH.Kart.vCardStatistic', name: 'vCardStatistic'}));
    fireEvent.click(within(foot).getByRole('button', {name: /vCardStatistic/}));
    expect(ExplorerService.table).toHaveBeenLastCalledWith('DWH.Kart.vCardStatistic');
    await waitFor(() => expect(document.getElementById('ds-path')).toHaveTextContent('DWH.Kart.vCardStatistic'));
  });

  it('opens a table without a star with "Tablo", the default tone and no neighbours', async () => {
    vi.mocked(ExplorerService.table).mockResolvedValue(tableDetail({key: 'DWH.Yok.vHayalet', groups: []}));
    show('DWH.Yok.vHayalet');
    await screen.findByText('CardLimitAmount');
    expect(document.getElementById('ds-kicker')).toHaveTextContent(message('dossier.kicker'));
    expect(document.getElementById('ds-name')).toHaveTextContent('vHayalet');
    expect(panel().style.getPropertyValue('--hue')).toBe('190');
    expect(document.getElementById('ds-foot')).toHaveClass('hidden');
  });

  it('says why a table could not be read', async () => {
    vi.mocked(ExplorerService.table).mockRejectedValue(new ApiError(404, 'Kayıt bulunamadı', 'table_not_found'));
    show();
    expect(
      await screen.findByText(message('dossier.failed', {message: message('explorer.error.table_not_found')})),
    ).toHaveClass('ds-empty');
  });

  it('drops a late answer for the table opened before', async () => {
    let answerFirst: (d: TableDetail) => void = () => undefined;
    vi.mocked(ExplorerService.table)
      .mockImplementationOnce(() => new Promise((resolve) => (answerFirst = resolve)))
      .mockResolvedValueOnce(tableDetail({columns: [column('SecondTableColumn')]}));
    show();
    fireEvent.click(screen.getByRole('button', {name: 'aç'}));
    await screen.findByText('SecondTableColumn');
    await act(async () => answerFirst(tableDetail({columns: [column('FirstTableColumn')]})));
    expect(screen.queryByText('FirstTableColumn')).toBeNull();
  });

  it('copies the key and says so for 1.4 seconds', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {value: {writeText: write}, configurable: true});
    show();
    const copy = screen.getByRole('button', {name: message('dossier.copy')});
    expect(copy).toHaveAttribute('title', message('dossier.copyTip'));
    await act(async () => fireEvent.click(copy));
    expect(write).toHaveBeenCalledWith('DWH.Kart.vCardLimit1');
    expect(copy).toHaveTextContent(message('dossier.copied'));
    await act(async () => vi.advanceTimersByTime(1400));
    expect(copy).toHaveTextContent(message('dossier.copy'));
    write.mockRejectedValue(new Error('no'));
    await act(async () => fireEvent.click(copy));
    expect(copy).toHaveTextContent(message('dossier.copyFailed'));
    vi.useRealTimers();
  });

  it('takes the focus to "Kapat", keeps Tab inside, goes to the search with "/" and gives the focus back on Esc', async () => {
    const opener = show();
    await screen.findByText('CardLimitAmount');
    const close = screen.getByRole('button', {name: message('dossier.close')});
    expect(document.activeElement).toBe(close);
    const buttons = within(panel()).getAllByRole('button');
    buttons[buttons.length - 1].focus();
    fireEvent.keyDown(panel(), {key: 'Tab'});
    expect(panel().contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, {key: '/'});
    expect(document.activeElement).toBe(screen.getByRole('searchbox'));
    const pageKeys = vi.fn();
    document.addEventListener('keydown', pageKeys);
    fireEvent.keyDown(document, {key: 'Escape'});
    document.removeEventListener('keydown', pageKeys);
    // The file's Esc comes first and is not seen by the page (it would stop an analysis).
    expect(pageKeys).not.toHaveBeenCalled();
    expect(panel()).not.toHaveClass('on');
    expect(panel()).toHaveAttribute('aria-hidden', 'true');
    expect(document.documentElement).not.toHaveClass('dossier-open');
    expect(document.activeElement).toBe(opener);
  });
});
