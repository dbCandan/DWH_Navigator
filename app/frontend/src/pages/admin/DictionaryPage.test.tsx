import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {DictionaryService} from '@/services/dictionary';
import {dictionaryState, table} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {DictionaryTable} from '@/types/dictionary';

const CHURN = table('SYNDM.AIS.vChurnModelInput', {group: 'Analitik', domain: 'Model', description: 'Müşteri kaybı modeli girdisi.', columns: 152});
const BRANCH = table('SYNDM.BRN.vBranch', {group: 'Şube', description: 'Şube listesi.', columns: 4});
const CAMPAIGN_CFM = table('SYNDM.CFM.vCampaign', {group: 'Kampanya', columns: 5});
const CAMPAIGN_CMP = table('SYNDM.CMP.vCampaign', {group: 'Kampanya', columns: 7});
const TABLES = [CHURN, BRANCH, CAMPAIGN_CFM, CAMPAIGN_CMP];

function serve(tables: DictionaryTable[] = TABLES, state = dictionaryState()) {
  vi.mocked(DictionaryService.state).mockResolvedValue(state);
  vi.mocked(DictionaryService.tables).mockResolvedValue(tables);
}

describe('Sözlük page (dictionary-management Requirement 13-15)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('points to the source before the first version and offers no export', async () => {
    renderApp('/admin/sozluk');
    const connect = await screen.findByRole('button', {name: message('dictionary.empty.connect')}, {timeout: 5000});
    expect(screen.getByRole('heading', {level: 2, name: message('dictionary.empty.title')})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: message('dictionary.export.button')})).toBeNull();
    expect(screen.queryByRole('button', {name: message('dictionary.view.tables')})).toBeNull();
    expect(document.querySelector('#nav-sozluk .bdg')).toHaveClass('bdg', 'warn');
    expect(document.querySelector('#nav-sozluk .bdg')).toHaveAttribute('title', message('admin.badge.noDictionary'));
    expect(screen.getByText(message('admin.sys.dictionaryNone'))).toBeInTheDocument();
    expect(screen.getByText(message('admin.sys.indexEmpty'))).toBeInTheDocument();
    const host = await screen.findByLabelText(message('dictionary.source.host'));
    fireEvent.click(connect);
    expect(host).toHaveFocus();
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

  it('keeps the chosen view in the address, so a reload or a link opens it', async () => {
    serve();
    renderApp('/admin/sozluk?gorunum=surumler');
    expect(await screen.findByRole('button', {name: message('dictionary.view.versions')})).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.view.source')}));
    expect(screen.getByRole('button', {name: message('dictionary.view.source')})).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', {name: message('dictionary.view.versions')})).toHaveAttribute('aria-pressed', 'false');
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

  it('offers no workbook import: no picker, no drop area, and a dropped file is left alone', async () => {
    serve();
    renderApp('/admin/bakim');
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    const transfer = {types: ['Files'], files: [new File(['PK'], 'sozluk.xlsx')]};
    fireEvent.dragEnter(window, {dataTransfer: transfer});
    fireEvent.drop(window, {dataTransfer: transfer});
    expect(document.getElementById('file')).toBeNull();
    expect(document.getElementById('dropzone')).toBeNull();
    expect('importWorkbook' in DictionaryService).toBe(false);
    expect('template' in DictionaryService).toBe(false);
  });

  it('downloads the export through the shared client and reports a failure', async () => {
    serve();
    const exported = vi.spyOn(DictionaryService, 'exportWorkbook').mockRejectedValue(new ApiError(500, 'x'));
    renderApp('/admin/sozluk');
    fireEvent.click(await screen.findByRole('button', {name: message('dictionary.export.button')}));
    expect(exported).toHaveBeenCalled();
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
