import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {DictionaryService} from '@/services/dictionary';
import {DictionarySyncService} from '@/services/dictionarySync';
import {answerConfirm, dictionarySource, dictionaryState, dictionaryVersion, syncChange, syncDetail, syncRun, table} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {SyncRunSummary} from '@/types/dictionarySync';

const CONFIGURED = dictionarySource({configured: true, host: 'edw.kurum.local', database: 'EDWUTIL', username: 'navigator', has_password: true});

function serve({runs = [] as SyncRunSummary[], source = CONFIGURED, state = dictionaryState()} = {}) {
  vi.mocked(DictionaryService.state).mockResolvedValue(state);
  vi.mocked(DictionaryService.tables).mockResolvedValue([table('EDWDM.DBO.vMusteri')]);
  vi.mocked(DictionarySyncService.source).mockResolvedValue(source);
  vi.mocked(DictionarySyncService.runs).mockResolvedValue({items: runs, total: runs.length, page: 1, page_size: 20});
  vi.spyOn(DictionarySyncService, 'preview').mockResolvedValue(PREVIEW);
}

const PREVIEW = {
  has_changes: true,
  scope: {scope_tables: 1, scope_columns: 3, scope_code_changed: 2},
  tables_needing_model: 1,
  rows_to_describe: 3,
  objects_to_describe: 1,
  model_calls: 9,
  average_call_seconds: 20,
  estimated_seconds: 90,
  requires_approval: true,
};

/** The update button opens the preview; its start button starts the run. */
async function startFromPreview(update: HTMLElement) {
  fireEvent.click(update);
  fireEvent.click(await button('dictionary.preview.start'));
}

/** The first look waits for the page's lazy chunk, which a busy test run can hold up. */
const LOADED = {timeout: 5000};
const button = (key: string, values?: Record<string, string | number>) => screen.findByRole('button', {name: message(key, values)}, LOADED);
const openView = async (key: string) => fireEvent.click(await button(key));

/** Opens a run's report from the history. */
async function openReport(run: SyncRunSummary) {
  await openView('dictionary.view.runs');
  fireEvent.click(await screen.findByText(message(`dictionary.sync.status.${run.status}`), {selector: 'td .pill'}));
  return screen.findByRole('dialog', {name: message('dictionary.report.title')});
}

describe('dictionary sync on the Sözlük page (dictionary-sync Requirement 1, 2, 9, 10, 12)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    clearAuth();
  });

  it('defaults the database, keeps the saved password when the field is empty and shows the test counts', async () => {
    serve({source: dictionarySource()});
    const save = vi.spyOn(DictionarySyncService, 'saveSource').mockResolvedValue(CONFIGURED);
    const test = vi.spyOn(DictionarySyncService, 'testSource').mockResolvedValue({
      ok: true,
      message: '',
      table_count: 1200,
      column_count: 11136,
      last_change_at: null,
      missing_databases: ['ERPDM'],
    });
    renderApp('/admin/sozluk');
    await openView('dictionary.view.source');
    expect(await screen.findByLabelText(message('dictionary.source.database'))).toHaveValue('EDWUTIL');
    expect(await button('dictionary.sync.button')).toBeDisabled();
    expect(await button('dictionary.source.save')).toBeDisabled();

    fireEvent.change(screen.getByLabelText(message('dictionary.source.host')), {target: {value: ' edw.kurum.local '}});
    fireEvent.change(screen.getByLabelText(message('dictionary.source.username')), {target: {value: 'navigator'}});
    fireEvent.click(await button('dictionary.source.test'));
    expect(await screen.findByText(message('dictionary.source.testOk', {tables: '1.200', columns: '11.136'}))).toHaveClass('msg', 'ok');
    expect(screen.getByText(message('dictionary.source.missingDatabases', {names: 'ERPDM'}))).toHaveClass('msg', 'warn');
    const body = {host: 'edw.kurum.local', port: 1433, database: 'EDWUTIL', username: 'navigator', encrypt: true};
    expect(test).toHaveBeenCalledWith(body);

    fireEvent.click(await button('dictionary.source.save'));
    expect(await screen.findByText(message('dictionary.source.saved'))).toBeInTheDocument();
    expect(save).toHaveBeenCalledWith(body);
    expect(await screen.findByText(message('dictionary.source.passwordKept'))).toBeInTheDocument();
    expect(await button('dictionary.sync.button')).toBeEnabled();
  });

  it('sends a typed password once, clears it after saving and shows a failed test', async () => {
    serve();
    const save = vi.spyOn(DictionarySyncService, 'saveSource').mockResolvedValue(CONFIGURED);
    vi.spyOn(DictionarySyncService, 'testSource')
      .mockResolvedValueOnce({ok: false, message: 'Oturum açılamadı.', table_count: 0, column_count: 0, last_change_at: null})
      .mockRejectedValueOnce(new ApiError(502, 'iç ayrıntı', 'dictionary_source_unavailable'));
    renderApp('/admin/sozluk');
    await openView('dictionary.view.source');
    const password = await screen.findByLabelText(message('dictionary.source.password'));
    fireEvent.change(password, {target: {value: 'test-parola'}});
    fireEvent.click(await button('dictionary.source.test'));
    expect(await screen.findByText('Oturum açılamadı.')).toHaveClass('msg', 'bad');
    fireEvent.click(await button('dictionary.source.test'));
    expect(await screen.findByText(message('admin.error.dictionary_source_unavailable'))).toHaveClass('msg', 'bad');
    expect(screen.queryByText('iç ayrıntı')).toBeNull();
    fireEvent.click(await button('dictionary.source.save'));
    await waitFor(() => expect(password).toHaveValue(''));
    expect(save).toHaveBeenCalledWith(expect.objectContaining({password: 'test-parola'}));
  });

  it('starts a run, follows it every two seconds and opens the report when it ends', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    serve();
    const running = syncRun({status: 'running', phase: 'reading', finished_at: null});
    const start = vi.spyOn(DictionarySyncService, 'start').mockResolvedValue(running);
    const read = vi
      .spyOn(DictionarySyncService, 'run')
      .mockResolvedValueOnce(syncDetail({...running, phase: 'filling', progress_done: 3, progress_total: 12}))
      .mockResolvedValue(syncDetail({counts: {tables_added: 2}}));
    renderApp('/admin/sozluk');
    const update = await button('dictionary.sync.button');
    await waitFor(() => expect(update).toBeEnabled());
    await startFromPreview(update);
    // The window follows the run; hidden, the run goes on and the page card shows it.
    const steps = await screen.findByRole('list', {name: message('dictionary.update.steps')});
    expect(within(steps).getByText(message('dictionary.sync.phase.reading')).closest('li')).toHaveAttribute('aria-current', 'step');
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.update.hide')}));
    expect(screen.queryByRole('dialog', {name: message('dictionary.update.title')})).toBeNull();
    expect(await screen.findByRole('heading', {level: 2, name: message('dictionary.sync.running')})).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
    expect(update).toBeEnabled();
    expect(screen.getByText(message('dictionary.sync.phase.reading'))).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(screen.getByText(message('dictionary.sync.phase.filling'))).toBeInTheDocument();
    expect(screen.getByText(message('dictionary.sync.progress', {done: 3, total: 12}))).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '25');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    const report = await screen.findByRole('dialog', {name: message('dictionary.report.title')});
    expect(within(report).getByText(message('dictionary.report.count.tables_added'), {selector: '.k'}).closest('.it')).toHaveTextContent('2');
    expect(screen.queryByRole('heading', {level: 2, name: message('dictionary.sync.running')})).toBeNull();
    const reads = read.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(read.mock.calls.length).toBe(reads);
  });

  it('shows what an update would look at before it starts, and starts nothing without changes', async () => {
    serve();
    const start = vi.spyOn(DictionarySyncService, 'start');
    renderApp('/admin/sozluk');
    const update = await button('dictionary.sync.button');
    await waitFor(() => expect(update).toBeEnabled());
    fireEvent.click(update);
    const panel = await screen.findByRole('region', {name: message('dictionary.preview.title')});
    expect(within(panel).getByText(message('dictionary.preview.calls'), {selector: '.k'}).closest('.it')).toHaveTextContent('9');
    expect(within(panel).getByText(message('dictionary.preview.approval'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.edit.cancel')}));
    expect(screen.queryByRole('region', {name: message('dictionary.preview.title')})).toBeNull();
    vi.mocked(DictionarySyncService.preview).mockResolvedValue({...PREVIEW, has_changes: false, model_calls: 0, estimated_seconds: 0});
    fireEvent.click(update);
    expect(await screen.findByText(message('dictionary.preview.noChange'))).toBeInTheDocument();
    expect(screen.getByRole('button', {name: message('dictionary.preview.start')})).toBeDisabled();
    expect(start).not.toHaveBeenCalled();
  });

  it('finds a running run on load, survives a failed read and stops reading after leaving the page', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    const running = syncRun({status: 'running', phase: 'comparing', finished_at: null});
    serve({runs: [running]});
    const read = vi
      .spyOn(DictionarySyncService, 'run')
      .mockRejectedValueOnce(new ApiError(500, 'x'))
      .mockResolvedValue(syncDetail({...running, phase: 'indexing'}));
    renderApp('/admin/sozluk');
    expect(await screen.findByText(message('dictionary.sync.phase.comparing'), {}, LOADED)).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getByText(message('dictionary.sync.phase.indexing'))).toBeInTheDocument();
    expect(read).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('link', {name: message('admin.page.bakim.label')}));
    await screen.findByRole('heading', {level: 1, name: message('admin.page.bakim.label')});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('follows the run the server names when another one is already going', async () => {
    serve();
    vi.spyOn(DictionarySyncService, 'start').mockRejectedValue(new ApiError(409, 'x', 'dictionary_sync_in_progress'));
    renderApp('/admin/sozluk');
    const update = await button('dictionary.sync.button');
    await waitFor(() => expect(update).toBeEnabled());
    vi.mocked(DictionarySyncService.runs).mockResolvedValue({
      items: [syncRun({status: 'running', phase: 'reading', finished_at: null})],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await startFromPreview(update);
    expect(await screen.findByText(message('admin.error.dictionary_sync_in_progress'))).toBeInTheDocument();
    expect((await screen.findAllByText(message('dictionary.sync.phase.reading'))).length).toBeGreaterThan(0);
  });

  it('opens the update window at once, keeps the run going when it closes and opens it again from the page', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    serve();
    let answer: (value: typeof PREVIEW) => void = () => undefined;
    vi.mocked(DictionarySyncService.preview).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const running = syncRun({status: 'running', phase: 'describing', finished_at: null, progress_done: 2, progress_total: 9});
    vi.spyOn(DictionarySyncService, 'start').mockResolvedValue(running);
    const read = vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail(running));
    renderApp('/admin/sozluk');
    const update = await button('dictionary.sync.button');
    await waitFor(() => expect(update).toBeEnabled());
    fireEvent.click(update);
    const window = screen.getByRole('dialog', {name: message('dictionary.update.title')});
    expect(within(window).getByText(message('dictionary.update.preparing'))).toBeInTheDocument();
    expect(within(window).getByText(message('dictionary.update.previewStep.read'))).toBeInTheDocument();
    await act(async () => answer(PREVIEW));
    fireEvent.click(await button('dictionary.preview.start'));
    const steps = await screen.findByRole('list', {name: message('dictionary.update.steps')});
    const current = within(steps).getByText(message('dictionary.sync.phase.describing')).closest('li');
    expect(current).toHaveAttribute('aria-current', 'step');
    expect(current).toHaveTextContent(message('dictionary.sync.progress', {done: 2, total: 9}));
    expect(within(steps).getByText(message('dictionary.sync.phase.comparing')).closest('li')).toHaveClass('done');
    expect(within(steps).getByText(message('dictionary.sync.phase.verifying')).closest('li')).toHaveClass('waiting');

    fireEvent.click(screen.getByRole('button', {name: message('admin.drawer.close')}));
    expect(screen.queryByRole('dialog', {name: message('dictionary.update.title')})).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(read).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: message('dictionary.update.details')}));
    expect(await screen.findByRole('list', {name: message('dictionary.update.steps')})).toBeInTheDocument();

    // The run ends while the window is open: the window says so and offers the report.
    read.mockResolvedValue(syncDetail({counts: {tables_added: 2}}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    fireEvent.click(await button('dictionary.sync.openReport'));
    expect(await screen.findByRole('dialog', {name: message('dictionary.report.title')})).toBeInTheDocument();
  });

  it('reports the counts with "Ambarda bulunmayan" and "Yazımı düzeltilen", the versions, the model and the warnings', async () => {
    const run = syncRun({counts: {tables_excluded: 4, columns_excluded: 17, tables_corrected: 1, columns_corrected: 6, fields_filled: 80}});
    serve({runs: [run]});
    vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail({...run, warnings: ['Satır 4 atlandı']}));
    const report = await (renderApp('/admin/sozluk'), openReport(run));
    const fact = (key: string) => within(report).findByText(message(`dictionary.report.count.${key}`), {selector: '.k'});
    expect((await fact('tables_excluded')).closest('.it')).toHaveTextContent('4');
    expect(message('dictionary.report.count.tables_excluded')).toContain('Ambarda bulunmayan');
    expect((await fact('columns_excluded')).closest('.it')).toHaveTextContent('17');
    expect((await fact('tables_corrected')).closest('.it')).toHaveTextContent('1');
    expect((await fact('columns_corrected')).closest('.it')).toHaveTextContent('6');
    expect(message('dictionary.report.count.columns_corrected')).toContain('Yazımı düzeltilen');
    expect(within(report).getByText('aaaaaaaaaaaa')).toBeInTheDocument();
    expect(within(report).getByText('bbbbbbbbbbbb')).toBeInTheDocument();
    expect(within(report).getByText('org/qwen-32b')).toBeInTheDocument();
    expect(within(report).getByText('Satır 4 atlandı')).toBeInTheDocument();
  });

  it('filters and pages the changes on the server and shows both spellings of a corrected name', async () => {
    const run = syncRun();
    serve({runs: [run]});
    vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail(run));
    const changes = vi.mocked(DictionarySyncService.changes).mockImplementation(async (_id, {kind, page}) => ({
      items:
        kind === 'column_corrected'
          ? [syncChange({kind, column_name: 'MusteriNo', old_value: 'MusteriNoo', new_value: 'MusteriNo'})]
          : [syncChange({new_value: `sayfa ${page}`})],
      total: kind ? 1 : 120,
      page,
      page_size: 50,
    }));
    const report = await (renderApp('/admin/sozluk'), openReport(run));
    expect(await within(report).findByText('sayfa 1')).toBeInTheDocument();
    fireEvent.click(within(report).getByRole('button', {name: message('dictionary.pager.next')}));
    expect(await within(report).findByText('sayfa 2')).toBeInTheDocument();

    const kind = within(report).getByRole('combobox', {name: message('dictionary.changes.kind')});
    expect(within(kind).getByRole('option', {name: message('dictionary.changes.kind.table_corrected')})).toBeInTheDocument();
    fireEvent.change(kind, {target: {value: 'column_corrected'}});
    const old = await within(report).findByText('MusteriNoo');
    const row = old.closest('tr') as HTMLElement;
    expect(within(row).getByText(message('dictionary.changes.kind.column_corrected'))).toBeInTheDocument();
    const cells = within(row).getAllByRole('cell');
    expect(cells[3]).toHaveTextContent('MusteriNoo');
    expect(cells[4]).toHaveTextContent('MusteriNo');
    expect(changes).toHaveBeenLastCalledWith(run.public_id, {kind: 'column_corrected', search: '', page: 1, pageSize: 50});

    fireEvent.change(within(report).getByRole('searchbox', {name: message('dictionary.changes.search')}), {target: {value: ' musteri '}});
    await waitFor(() =>
      expect(changes).toHaveBeenLastCalledWith(run.public_id, {kind: 'column_corrected', search: 'musteri', page: 1, pageSize: 50}),
    );
  });

  it('shows the failure class of a run, the target one included, and never a raw code', async () => {
    const run = syncRun({status: 'failed', error_code: 'dictionary_target_unavailable', error_message: 'ERPDM okunamadı.', new_version: ''});
    serve({runs: [run]});
    vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail(run));
    const report = await (renderApp('/admin/sozluk'), openReport(run));
    expect(await within(report).findByText(message('admin.error.dictionary_target_unavailable'))).toBeInTheDocument();
    expect(within(report).getByText('ERPDM okunamadı.')).toBeInTheDocument();
    expect(within(report).queryByText('dictionary_target_unavailable')).toBeNull();
  });

  it('applies or rejects a waiting run only after the confirmation', async () => {
    const run = syncRun({status: 'pending_approval', counts: {tables_removed: 40}});
    serve({runs: [run]});
    vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail(run));
    const approve = vi.spyOn(DictionarySyncService, 'approve').mockResolvedValue(syncDetail({...run, status: 'completed'}));
    const reject = vi.spyOn(DictionarySyncService, 'reject');
    const confirm = answerConfirm(false, false, true);
    renderApp('/admin/sozluk');
    fireEvent.click(await button('dictionary.sync.openReport'));
    const report = await screen.findByRole('dialog', {name: message('dictionary.report.title')});
    expect(await within(report).findByText(message('dictionary.report.pendingNotice'))).toBeInTheDocument();
    fireEvent.click(within(report).getByRole('button', {name: message('dictionary.report.reject')}));
    expect(confirm).toHaveBeenLastCalledWith(message('dictionary.report.rejectConfirm'));
    expect(reject).not.toHaveBeenCalled();
    fireEvent.click(within(report).getByRole('button', {name: message('dictionary.report.approve')}));
    expect(approve).not.toHaveBeenCalled();
    fireEvent.click(within(report).getByRole('button', {name: message('dictionary.report.approve')}));
    expect(confirm).toHaveBeenLastCalledWith(message('dictionary.report.approveConfirm'));
    await waitFor(() => expect(approve).toHaveBeenCalledWith(run.public_id));
    await waitFor(() => expect(within(report).queryByRole('button', {name: message('dictionary.report.approve')})).toBeNull());
  });

  it('applies only the ticked suggestions', async () => {
    const run = syncRun();
    const term = {public_id: 's1', kind: 'term' as const, value: 'MUST', equivalents: ['müşteri'], note: '', status: 'pending' as const};
    const stop = {public_id: 's2', kind: 'stopword' as const, value: 'tablo', equivalents: [], note: 'Sık geçiyor', status: 'pending' as const};
    const done = {public_id: 's3', kind: 'term' as const, value: 'HSP', equivalents: ['hesap'], note: '', status: 'applied' as const};
    serve({runs: [run]});
    vi.spyOn(DictionarySyncService, 'run').mockResolvedValue(syncDetail({...run, suggestions: [term, stop, done]}));
    const apply = vi
      .spyOn(DictionarySyncService, 'applySuggestions')
      .mockResolvedValue(syncDetail({...run, suggestions: [{...term, status: 'applied'}, stop, done]}));
    const report = await (renderApp('/admin/sozluk'), openReport(run));
    const none = await within(report).findByRole('button', {name: message('dictionary.suggestions.apply', {count: 0})});
    expect(none).toBeDisabled();
    expect(within(report).getByRole('checkbox', {name: 'HSP'})).toBeDisabled();
    fireEvent.click(within(report).getByRole('checkbox', {name: 'MUST'}));
    fireEvent.click(within(report).getByRole('button', {name: message('dictionary.suggestions.apply', {count: 1})}));
    await waitFor(() => expect(apply).toHaveBeenCalledWith(run.public_id, ['s1']));
    await waitFor(() => expect(within(report).getByRole('checkbox', {name: 'MUST'})).toBeDisabled());
  });

  it('offers "Bu sürüme dön" only where it is possible, after a confirmation, and follows the run', async () => {
    serve();
    const old = dictionaryVersion();
    const gone = dictionaryVersion({public_id: 'gone', version: 'cccccccccccc-90', can_restore: false});
    vi.mocked(DictionarySyncService.versions).mockResolvedValue([old, gone]);
    const restore = vi
      .spyOn(DictionarySyncService, 'restore')
      .mockRejectedValueOnce(new ApiError(410, 'x', 'dictionary_version_expired'))
      .mockResolvedValue(syncRun({kind: 'geri_donus', status: 'running', phase: 'indexing', finished_at: null}));
    const confirm = answerConfirm(false, true);
    renderApp('/admin/sozluk');
    await openView('dictionary.view.versions');
    const buttons = await screen.findAllByRole('button', {name: message('dictionary.versions.restore')});
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(confirm).toHaveBeenCalledWith(message('dictionary.versions.restoreConfirm', {version: 'aaaaaaaaaaaa'}));
    expect(restore).not.toHaveBeenCalled();
    fireEvent.click(buttons[0]);
    expect(await screen.findByText(message('admin.error.dictionary_version_expired'))).toBeInTheDocument();
    fireEvent.click(buttons[0]);
    expect(await screen.findByRole('heading', {level: 2, name: message('dictionary.sync.runningRestore')})).toBeInTheDocument();
    expect(restore).toHaveBeenCalledWith(old.public_id);
    expect(buttons[0]).toBeDisabled();
  });
});
