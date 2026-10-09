import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {DictionaryService} from '@/services/dictionary';
import {answerConfirm, dictionaryState, indexState, table} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {DictionaryImported, DictionaryTable} from '@/types/dictionary';

const CHURN = table('SYNDM.AIS.vChurnModelInput', {group: 'Analitik', domain: 'Model', description: 'Müşteri kaybı modeli girdisi.', columns: 152});
const BRANCH = table('SYNDM.BRN.vBranch', {group: 'Şube', description: 'Şube listesi.', columns: 4});
const CAMPAIGN_CFM = table('SYNDM.CFM.vCampaign', {group: 'Kampanya', columns: 5});
const CAMPAIGN_CMP = table('SYNDM.CMP.vCampaign', {group: 'Kampanya', columns: 7});
const TABLES = [CHURN, BRANCH, CAMPAIGN_CFM, CAMPAIGN_CMP];

function serve(tables: DictionaryTable[] = TABLES, state = dictionaryState()) {
  vi.mocked(DictionaryService.state).mockResolvedValue(state);
  vi.mocked(DictionaryService.tables).mockResolvedValue(tables);
}

const xlsx = (name = 'sozluk.xlsx') => new File(['PK'], name, {type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
const pick = (file: File) => fireEvent.change(document.getElementById('file') as HTMLInputElement, {target: {files: [file]}});

function imported(changed: boolean, warnings: string[] = []): DictionaryImported {
  const {active} = dictionaryState({warning_count: warnings.length});
  const {warnings: _kept, ...version} = active!;
  void _kept;
  return {changed, version, warnings, index: indexState()};
}

describe('Sözlük page (dictionary-management Requirement 13-15)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('offers the drop area and the template before the first import', async () => {
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);
    renderApp('/admin/sozluk');
    const area = await screen.findByRole('button', {name: new RegExp(message('dictionary.empty.title'))});
    expect(screen.getByText(message('dictionary.templateCard.title'))).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: message('dictionary.export.button')})).toBeNull();
    expect(document.querySelector('#nav-sozluk .bdg')).toHaveClass('bdg', 'warn');
    expect(document.querySelector('#nav-sozluk .bdg')).toHaveAttribute('title', message('admin.badge.noDictionary'));
    expect(screen.getByText(message('admin.sys.dictionaryNone'))).toBeInTheDocument();
    expect(screen.getByText(message('admin.sys.indexEmpty'))).toBeInTheDocument();
    fireEvent.keyDown(area, {key: 'Enter'});
    fireEvent.keyDown(area, {key: ' '});
    expect(click).toHaveBeenCalledTimes(2);
  });

  it('shows the version, the index state and the tables, filters them and opens one', async () => {
    serve(TABLES, dictionaryState({warning_count: 3}));
    vi.spyOn(DictionaryService, 'table').mockResolvedValue({
      key: CHURN.key,
      object: {ObjectDescription: 'Müşteri kaybı modeli girdisi.', DatasetGroup: 'Analitik', BusinessDomain: 'Model', Grain: '', KeyColumns: 'CustomerId', TimeColumns: ''},
      columns: [{ColumnName: 'CustomerId', Summary: 'Müşteri', Role: 'Anahtar', ColumnDescription: 'Müşteri numarası.', Synonyms: ''}],
    });
    renderApp('/admin/sozluk');
    const title = await screen.findByRole('heading', {level: 2, name: message('dictionary.tables.title', {count: 4})});
    expect(screen.getByText('abcdef123456').closest('.it')).toHaveAttribute('title', 'abcdef123456-130');
    expect(screen.getByText(message('dictionary.info.indexOk'))).toHaveClass('pill', 'ok');
    expect(screen.getByText(message('dictionary.info.warnings', {count: 3}))).toHaveClass('msg', 'warn');
    expect(screen.getByText(message('admin.sys.dictionary', {objects: 12, columns: 120}))).toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', {name: message('dictionary.tables.search')}), {target: {value: 'ŞUBE '}});
    expect(title).toHaveTextContent(message('dictionary.tables.titleFiltered', {count: 1, total: 4}));
    fireEvent.change(screen.getByRole('searchbox', {name: message('dictionary.tables.search')}), {target: {value: ''}});
    fireEvent.change(screen.getByRole('combobox', {name: message('dictionary.tables.group')}), {target: {value: 'Kampanya'}});
    expect(screen.getAllByText('vCampaign')).toHaveLength(2);
    expect(screen.getByText('SYNDM.CMP')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', {name: message('dictionary.tables.group')}), {target: {value: ''}});

    const row = screen.getByText('vChurnModelInput').closest('tr') as HTMLElement;
    expect(row).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(row, {key: ' '});
    const drawer = await screen.findByRole('dialog', {name: 'vChurnModelInput'});
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/sozluk/SYNDM.AIS.vChurnModelInput'));
    expect(await within(drawer).findByText(message('dictionary.table.columns', {count: 1}))).toBeInTheDocument();
    expect(within(drawer).getByText('Anahtar', {selector: '.role'})).toBeInTheDocument();
    expect(within(drawer).getByText('CustomerId', {selector: 'dd'})).toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole('button', {name: message('admin.drawer.close')}));
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/sozluk'));
  });

  it('opens a deep link in its drawer and says when the table is not in the dictionary', async () => {
    serve();
    vi.spyOn(DictionaryService, 'table').mockRejectedValue(new ApiError(404, 'Tablo sözlükte yok.', 'dictionary_table_not_found'));
    renderApp('/admin/sozluk/SYNDM.XX.vYok');
    const drawer = await screen.findByRole('dialog', {name: 'vYok'});
    await waitFor(() => expect(drawer.querySelector('.drawer-b')?.textContent).toBe(message('admin.error.dictionary_table_not_found')));
  });

  it('shows the first 200 tables and the rest on "Daha fazla"', async () => {
    serve(Array.from({length: 230}, (_, at) => table(`SYNDM.T.v${String(at).padStart(3, '0')}`)));
    renderApp('/admin/sozluk');
    const more = await screen.findByRole('button', {name: message('dictionary.tables.more', {count: 30})});
    expect(document.querySelectorAll('#d-list tbody tr')).toHaveLength(200);
    fireEvent.click(more);
    expect(document.querySelectorAll('#d-list tbody tr')).toHaveLength(230);
  });

  it('offers "İndeksi kur" when the index was built from another version', async () => {
    serve(TABLES, dictionaryState({}, 'eeeeeeeeeeee-99'));
    renderApp('/admin/sozluk');
    expect(await screen.findByRole('button', {name: message('dictionary.info.buildIndex')})).toHaveClass('btn', 'sm', 'primary');
    expect(document.querySelector('#sys .led.warn')).not.toBeNull();
  });

  it('refuses a file that is not .xlsx before any request', async () => {
    const send = vi.spyOn(DictionaryService, 'importWorkbook');
    renderApp('/admin/sozluk');
    await screen.findByText(message('dictionary.templateCard.title'));
    pick(new File(['a'], 'sozluk.csv'));
    expect(await screen.findByText(message('admin.excel.notExcel'))).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it('imports the first dictionary without asking and reports the counts and the first three warnings', async () => {
    const warnings = ['Satır 4: eksik veritabanı/şema/obje/kolon, atlandı', 'b', 'c', 'd'];
    const send = vi.spyOn(DictionaryService, 'importWorkbook').mockResolvedValue(imported(true, warnings));
    const confirm = answerConfirm(true);
    renderApp('/admin/sozluk');
    await screen.findByText(message('dictionary.templateCard.title'));
    serve();
    pick(xlsx());
    expect(await screen.findByText(message('dictionary.import.done'))).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    expect(send).toHaveBeenCalledWith(expect.objectContaining({name: 'sozluk.xlsx'}));
    expect(screen.getByText(message('dictionary.import.doneCounts', {columns: 120, objects: 12, source: 'sozluk_sentetik.xlsx'}))).toBeInTheDocument();
    expect(screen.getByText(message('dictionary.import.doneWarnings', {count: 4, warnings: warnings.slice(0, 3).join(' · ')}))).toBeInTheDocument();
    expect(await screen.findByRole('heading', {level: 2, name: message('dictionary.tables.title', {count: 4})})).toBeInTheDocument();
  });

  it('asks before replacing a dictionary and says when the content did not change', async () => {
    serve();
    const send = vi.spyOn(DictionaryService, 'importWorkbook').mockResolvedValue(imported(false));
    const confirm = answerConfirm(false, true);
    renderApp('/admin/sozluk');
    await screen.findByRole('heading', {level: 2, name: message('dictionary.tables.title', {count: 4})});
    pick(xlsx('yeni.xlsx'));
    expect(confirm).toHaveBeenCalledWith(message('dictionary.import.confirm', {name: 'yeni.xlsx'}));
    expect(send).not.toHaveBeenCalled();
    pick(xlsx('yeni.xlsx'));
    expect(await screen.findByText(message('dictionary.import.unchanged'))).toBeInTheDocument();
    expect(screen.getByText(message('dictionary.import.unchangedLine', {version: 'abcdef123456'}))).toBeInTheDocument();
  });

  it('shows the server sentence for an invalid workbook and the catalog text for other codes', async () => {
    const send = vi
      .spyOn(DictionaryService, 'importWorkbook')
      .mockRejectedValueOnce(new ApiError(422, '“Kolonlar” sayfasında kolon yok.', 'dictionary_workbook_invalid'))
      .mockRejectedValueOnce(new ApiError(409, 'iç ayrıntı', 'dictionary_import_in_progress'));
    renderApp('/admin/sozluk');
    await screen.findByText(message('dictionary.templateCard.title'));
    pick(xlsx());
    expect(await screen.findByText('“Kolonlar” sayfasında kolon yok.')).toBeInTheDocument();
    pick(xlsx());
    expect(await screen.findByText(message('admin.error.dictionary_import_in_progress'))).toBeInTheDocument();
    expect(screen.queryByText('iç ayrıntı')).toBeNull();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('imports a workbook dropped on another admin page but not on Kelimeler', async () => {
    serve();
    const send = vi.spyOn(DictionaryService, 'importWorkbook').mockResolvedValue(imported(true));
    answerConfirm(true);
    renderApp('/admin/bakim');
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    const files = [xlsx()];
    const transfer = {types: ['Files'], files};
    fireEvent.dragEnter(window, {dataTransfer: transfer});
    expect(screen.getByText(message('dictionary.drop'))).toBeVisible();
    fireEvent.drop(window, {dataTransfer: transfer});
    expect(screen.getByText(message('dictionary.drop'))).not.toBeVisible();
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/sozluk'));

    fireEvent.click(screen.getByRole('link', {name: message('admin.page.kelimeler.label')}));
    await screen.findByRole('heading', {level: 1, name: message('admin.page.kelimeler.label')});
    fireEvent.dragEnter(window, {dataTransfer: transfer});
    expect(screen.getByText(message('dictionary.drop'))).not.toBeVisible();
    fireEvent.drop(window, {dataTransfer: transfer});
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('downloads the export and the template through the shared client', async () => {
    serve();
    const exported = vi.spyOn(DictionaryService, 'exportWorkbook').mockResolvedValue('VeriSozlugu.xlsx');
    const template = vi.spyOn(DictionaryService, 'template').mockRejectedValue(new ApiError(500, 'x'));
    renderApp('/admin/sozluk');
    fireEvent.click(await screen.findByRole('button', {name: message('dictionary.export.button')}));
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.template.button')}));
    expect(exported).toHaveBeenCalled();
    expect(template).toHaveBeenCalled();
    expect(await screen.findByText(message('admin.download.failed'))).toBeInTheDocument();
  });

  it('lists the tables in the command palette and opens one from there', async () => {
    serve();
    vi.spyOn(DictionaryService, 'table').mockResolvedValue({key: BRANCH.key, object: null, columns: []});
    renderApp('/admin/genel');
    await screen.findByText(message('admin.sys.dictionary', {objects: 12, columns: 120}));
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    fireEvent.change(await screen.findByRole('textbox', {name: message('admin.palette.label')}), {target: {value: 'vbranch'}});
    expect(screen.getByText(message('admin.palette.tables'))).toBeInTheDocument();
    fireEvent.click(screen.getByText(message('admin.palette.tableTip', {where: 'Şube', columns: 4})));
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('/admin/sozluk/SYNDM.BRN.vBranch'));
    expect(await screen.findByText(message('dictionary.table.noDescription'))).toBeInTheDocument();
  });
});
