import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {formatDateTime} from '@/lib/format';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {SavedAnswersService} from '@/services/savedAnswers';
import {answerConfirm, recordDetail, recordPage, recordRow, recordSummary, SNAPSHOT_AT} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {RecordDetail, RecordRow, RecordStep} from '@/types/records';

const ALI = {public_id: '00000000-0000-4000-8000-0000000000b1', display_name: 'Ali Veli', kind: 'account' as const};
const AYSE = {public_id: '00000000-0000-4000-8000-0000000000b2', display_name: 'Ayşe Kaya', kind: 'account' as const};
const NO_FILTER = {period: '7d', flow: '', asked_by: '', q: ''};

const list = () => vi.mocked(AnalysisRecordsService.list);
const title = () => document.getElementById('a-title')?.textContent;
const drawer = () => screen.getByRole('dialog');
const where = () => screen.getByTestId('where').textContent;
const bodyRows = () => [...document.querySelectorAll<HTMLTableRowElement>('#a-list tbody tr')];

function serve(rows: RecordRow[], total = rows.length) {
  list().mockResolvedValue(recordPage({items: rows, total}));
  vi.mocked(AnalysisRecordsService.askers).mockResolvedValue({items: [ALI, AYSE]});
}

async function openPage(path = '/admin/analizler') {
  renderApp(path);
  await waitFor(() => expect(title()).toMatch(/^Sorular · /));
}

const step = (seq: number, parent: number | null, start: number, ms: number, overrides: Partial<RecordStep> = {}): RecordStep => ({
  seq,
  parent,
  name: `Adım ${seq}`,
  kind: 'step',
  key: null,
  start_ms: start,
  ms,
  status: 'ok',
  detail: '',
  ...overrides,
});

describe('Analizler page (analysis-records Requirement 16-22)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    clearAuth();
  });

  it('lists the filter\'s records with their indicators, list term, tables, reason and asker', async () => {
    const rows = [
      recordRow('Şube bazında mevduat', {table_keys: ['DWH.Ornek.vBranch', 'DWH.Ornek.vDeposit', 'DWH.Ornek.vRate'], duration_ms: 4500}),
      recordRow('Kredi kartı limiti', {
        origin: 'list',
        list_file_name: 'liste.xlsx',
        list_position: 3,
        flow: 'unavailable',
        verdict: null,
        table_keys: [],
        unavailable_reason: 'Sözlükte yok',
        asked_by: AYSE,
      }),
      recordRow('Hatalı soru', {flow: 'failed', verdict: null, table_keys: [], error: {code: 'analysis_failed', message: 'Beklenmeyen hata'}}),
    ];
    serve(rows);
    vi.mocked(AnalysisRecordsService.summary).mockResolvedValue(
      recordSummary({count: 3, with_result: 1, with_tables: 1, flows: {analyst: 1, reused: 0, unavailable: 1, cancelled: 0, failed: 1, interrupted: 0}, analyst_p50_ms: 4500, analyst_p90_ms: 4500}),
    );
    await openPage();
    expect(screen.getByText(message('admin.page.analizler.description'))).toBeInTheDocument();
    expect(title()).toBe(message('records.list.title', {period: message('records.periodName.7d'), count: 3}));
    expect(list()).toHaveBeenCalledWith(NO_FILTER, 1);
    expect(AnalysisRecordsService.summary).toHaveBeenCalledWith(NO_FILTER, SNAPSHOT_AT);
    expect([...document.querySelectorAll('#a-kpis .kpi .v')].map((v) => v.textContent)).toEqual(['3', '%100', '%33', '4,5 sn']);
    expect(document.querySelector('#a-kpis .kpi:nth-child(3) .s')).toHaveTextContent(message('records.kpi.analystFailed', {count: 2}));

    expect([...document.querySelectorAll('#a-list th')].map((th) => th.textContent)).toEqual([
      message('records.col.when'),
      message('records.col.question'),
      message('records.col.flow'),
      message('records.col.duration'),
    ]);
    const [first, second, third] = bodyRows();
    expect(first.querySelector('.a')?.textContent).toBe('VAR' + message('records.moreTables', {name: 'vBranch', count: 2}));
    expect(first.querySelector('.dur')).toHaveTextContent('4,5 sn');
    expect(first.querySelector('.flow')).toHaveTextContent('● Analist');
    expect(within(second).getByTitle(message('records.originTip'))).toHaveTextContent(message('records.origin', {file: 'liste.xlsx', position: 3}));
    expect(second.querySelector('.a')).toHaveTextContent('—Sözlükte yok');
    expect(second.querySelector('.flow')).toHaveClass('flow', 'yapılamadı');
    expect(second.querySelector('.note')).toHaveTextContent('Ayşe Kaya');
    expect(third.querySelector('.a')).toHaveTextContent('—Beklenmeyen hata');
    expect(within(screen.getByRole('combobox', {name: message('records.asker.label')})).getAllByRole('option').map((o) => o.textContent)).toEqual([
      message('records.asker.all'),
      'Ali Veli',
      'Ayşe Kaya',
    ]);
    expect(screen.getByTitle(message('records.live.tip'))).toHaveTextContent(message('records.live.label'));
  });

  it('says when nothing was asked yet, when the filter matches nothing and when the list cannot be read', async () => {
    const view = renderApp('/admin/analizler');
    expect(await screen.findByText(message('records.empty.none'))).toBeInTheDocument();
    view.unmount();
    vi.mocked(AnalysisRecordsService.askers).mockResolvedValue({items: [ALI]});
    const again = renderApp('/admin/analizler');
    expect(await screen.findByText(message('records.empty.filter'))).toBeInTheDocument();
    again.unmount();
    list().mockRejectedValue(new ApiError(500, 'x'));
    renderApp('/admin/analizler');
    expect(await screen.findByText(message('records.failed', {reason: message('ai.error.unexpected', {status: 500})}))).toHaveClass('msg', 'bad');
  });

  it('sends the period, flow, asker and text (300 ms after typing) and reloads from the start', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    serve([recordRow('Mevduat')]);
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.period.30d')}));
    await waitFor(() => expect(list()).toHaveBeenLastCalledWith({...NO_FILTER, period: '30d'}, 1));
    expect(screen.getByRole('button', {name: message('records.period.30d')})).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(title()).toBe(message('records.list.title', {period: message('records.periodName.30d'), count: 1})));

    fireEvent.change(screen.getByRole('combobox', {name: message('records.flowFilter.label')}), {target: {value: 'reused'}});
    await waitFor(() => expect(list()).toHaveBeenLastCalledWith({...NO_FILTER, period: '30d', flow: 'reused'}, 1));
    fireEvent.change(screen.getByRole('combobox', {name: message('records.asker.label')}), {target: {value: AYSE.public_id}});
    await waitFor(() =>
      expect(list()).toHaveBeenLastCalledWith({...NO_FILTER, period: '30d', flow: 'reused', asked_by: AYSE.public_id}, 1),
    );

    const calls = list().mock.calls.length;
    const search = screen.getByRole('searchbox', {name: message('records.search.label')});
    expect(search).toHaveAttribute('placeholder', message('records.search.placeholder'));
    fireEvent.change(search, {target: {value: ' işl'}});
    fireEvent.change(search, {target: {value: ' işlem '}});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(list().mock.calls.length).toBe(calls);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });
    await waitFor(() =>
      expect(list()).toHaveBeenLastCalledWith({period: '30d', flow: 'reused', asked_by: AYSE.public_id, q: 'işlem'}, 1),
    );
    expect(list().mock.calls.length).toBe(calls + 1);
  });

  it('focuses the search box with "/"', async () => {
    await openPage();
    fireEvent.keyDown(document.body, {key: '/'});
    expect(document.activeElement).toBe(screen.getByRole('searchbox', {name: message('records.search.label')}));
  });

  it('adds the next page with the same until on "Daha fazla"', async () => {
    const firstPage = Array.from({length: 150}, (_, i) => recordRow(`Soru ${i}`));
    const secondPage = Array.from({length: 50}, (_, i) => recordRow(`Soru ${150 + i}`));
    list().mockImplementation(async (_filters, page = 1) =>
      recordPage({items: page === 1 ? firstPage : secondPage, total: 200, page}),
    );
    await openPage();
    expect(bodyRows()).toHaveLength(150);
    fireEvent.click(screen.getByRole('button', {name: message('records.more', {count: 50})}));
    await waitFor(() => expect(bodyRows()).toHaveLength(200));
    expect(list()).toHaveBeenLastCalledWith(NO_FILTER, 2, SNAPSHOT_AT);
    expect(screen.queryByRole('button', {name: /Daha fazla/})).toBeNull();
  });

  it('refreshes every 15 s keeping the shown rows, and stops when off, hidden or a drawer is open', async () => {
    vi.useFakeTimers({shouldAdvanceTime: true});
    const firstPage = Array.from({length: 150}, (_, i) => recordRow(`Soru ${i}`));
    list().mockImplementation(async (_filters, page = 1) => recordPage({items: page === 1 ? firstPage : [recordRow('Son')], total: 151, page}));
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.more', {count: 1})}));
    await waitFor(() => expect(bodyRows()).toHaveLength(151));
    list().mockClear();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    // A new until for the first page, then every shown page with it.
    expect(list().mock.calls).toEqual([
      [NO_FILTER, 1],
      [NO_FILTER, 2, SNAPSHOT_AT],
    ]);
    expect(bodyRows()).toHaveLength(151);

    list().mockClear();
    fireEvent.click(screen.getByRole('checkbox'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16000);
    });
    expect(list()).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox'));

    Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16000);
    });
    expect(list()).not.toHaveBeenCalled();
    Object.defineProperty(document, 'visibilityState', {value: 'visible', configurable: true});

    fireEvent.click(screen.getByRole('button', {name: message('records.performance')}));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16000);
    });
    expect(list()).not.toHaveBeenCalled();
    fireEvent.keyDown(document, {key: 'Escape'});

    fireEvent.click(screen.getByRole('button', {name: message('records.refresh')}));
    await waitFor(() => expect(list()).toHaveBeenCalledWith(NO_FILTER, 1));
  });

  it.each([
    [
      'analyst',
      {summary: 'VAR — Şube tablosu uygun.', verdict: 'VAR' as const, model: 'org/qwen-32b', llm_calls: 2, prompt_tokens: 12345, completion_tokens: 950},
      ['Dil modeli (org/qwen-32b)', 'Şube tablosu uygun.', message('records.detail.usageValue', {calls: 2, prompt: '12,3 k', completion: '950'})],
    ],
    [
      'reused',
      {reused: {at: '2026-10-07T08:00:00Z', query: 'şube mevduatı', match: 'same_meaning' as const}},
      ['Önceki cevap: aynı anlama gelen “şube mevduatı”'],
    ],
    ['unavailable', {verdict: null, unavailable_reason: 'Sözlükte yok'}, ['Analiz yapılamadı', message('records.detail.reason', {reason: 'Sözlükte yok'})]],
    ['cancelled', {verdict: null, error: {code: 'cancelled', message: 'Kullanıcı durdurdu'}}, ['Kullanıcı durdurdu', 'Hata: Kullanıcı durdurdu', 'durdu']],
    ['failed', {verdict: null, error: {code: 'analysis_failed', message: 'Beklenmeyen hata'}}, ['Hata: Beklenmeyen hata']],
    ['interrupted', {verdict: null, model: ''}, [message('records.by.interrupted'), message('records.timeline.none')]],
  ] as const)('opens a %s record from its deep link with its drawer content', async (flow, fields, texts) => {
    const row = recordRow('Şube bazında mevduat', {flow, origin: 'list', list_file_name: 'liste.xlsx', list_position: 4});
    serve([row]);
    vi.mocked(AnalysisRecordsService.detail).mockResolvedValue(recordDetail(row, fields as Partial<RecordDetail>));
    await openPage(`/admin/analizler/${row.public_id}`);
    const panel = await screen.findByRole('dialog', {name: 'Şube bazında mevduat'});
    expect(panel.closest('.drawer')).toHaveClass('drawer', 'wide');
    expect(within(panel).getByText(message('records.detail.sub', {at: formatDateTime(row.asked_at), asker: 'Ali Veli', duration: '12 sn'}))).toBeInTheDocument();
    expect(within(panel).getByText(message(`records.flow.${flow}`), {exact: false, selector: '.flow'})).toBeInTheDocument();
    for (const text of texts) expect(panel).toHaveTextContent(text);
    expect(panel).toHaveTextContent(message('records.detail.listValue', {file: 'liste.xlsx', position: 4}));
    expect(panel).toHaveTextContent(message('records.detail.keys'));
    expect(document.querySelector(`tr[data-id="${row.public_id}"]`)).toHaveClass('sel');
  });

  it('shows where the time went and the step timeline in tree order with indents and tooltips', async () => {
    const row = recordRow('Mevduat', {duration_ms: 10000});
    serve([row]);
    vi.mocked(AnalysisRecordsService.detail).mockResolvedValue(
      recordDetail(row, {
        table_keys: ['DWH.Ornek.vBranch'],
        phases: {queue: 900, saved_answer_lookup: 0, model_check: 500, rule_hints: 0, analyst_pick: 3000, analyst_write: 5000},
        steps_truncated: true,
        steps: [
          step(0, null, 0, 9000, {name: 'Analist akışı'}),
          step(3, 0, 4000, 5000, {name: '2. adım — kolon okuma ve rapor', key: 'analyst_report', detail: '3 tablo'}),
          step(1, 0, 1000, 3000, {name: '1. adım — aday seçimi', key: 'shortlist'}),
          step(2, 1, 1200, 2500, {
            name: 'LLM çağrısı',
            kind: 'llm',
            status: 'error',
            detail: 'org/qwen-32b — timeout',
            call: {outcome: 'timeout', http_status: null, prompt_tokens: 12345, completion_tokens: 0},
          }),
          step(4, 3, 9000, 0, {name: 'Yanıt JSON değil — onarım isteniyor', kind: 'event', status: 'warn', detail: 'deneme 1'}),
        ],
      }),
    );
    await openPage(`/admin/analizler/${row.public_id}`);
    const panel = await screen.findByRole('dialog', {name: 'Mevduat'});
    expect(within(panel).getByText('vBranch')).toHaveAttribute('title', 'DWH.Ornek.vBranch');
    expect(panel).toHaveTextContent(message('records.detail.where', {duration: '10 sn'}));
    // A queue wait under one second is left out.
    expect([...panel.querySelectorAll('ul.phases li')].map((li) => li.firstChild?.nextSibling?.textContent)).toEqual([
      message('records.phase.model_check'),
      message('records.phase.analyst_pick'),
      message('records.phase.analyst_write'),
    ]);
    const stack = [...panel.querySelectorAll<HTMLElement>('.stack i')];
    expect(stack.map((bar) => [bar.className, bar.style.width])).toEqual([
      ['ph-check', '5.00%'],
      ['ph-pick', '30.00%'],
      ['ph-write', '50.00%'],
    ]);

    const names = [...panel.querySelectorAll<HTMLElement>('.wf .nm')];
    expect(names.map((name) => [name.textContent, name.style.paddingLeft])).toEqual([
      ['Analist akışı', '0px'],
      ['1. adım — aday seçimi', '14px'],
      ['✕LLM çağrısı', '28px'],
      ['2. adım — kolon okuma ve rapor', '14px'],
      ['Yanıt JSON değil — onarım isteniyor', '28px'],
    ]);
    expect(names[2].title).toBe(
      ['LLM çağrısı (model çağrısı)', '+1,2 sn · 2,5 sn · 12,3 k → 0 token', message('records.outcome.timeout'), 'org/qwen-32b — timeout'].join('\n'),
    );
    const bar = panel.querySelectorAll<HTMLElement>('.wf .bar')[2];
    expect(bar).toHaveClass('bar', 'llm', 'error');
    expect([bar.style.left, bar.style.width]).toEqual(['12.00%', '25.00%']);
    expect([...panel.querySelectorAll('.wf .why')].map((why) => why.textContent)).toEqual(['org/qwen-32b — timeout', '3 tablo', 'deneme 1']);
    expect(panel.querySelectorAll('.wf .ms')[4]).toHaveTextContent(message('records.timeline.eventMark'));
    expect(panel).toHaveTextContent(message('records.timeline.truncated'));
    expect(panel).toHaveTextContent(message('records.timeline.legendWait'));
  });

  it('opens a row by click, Enter or Space, moves with ↓/↑ between loaded rows and closes with Esc', async () => {
    const rows = [recordRow('Birinci'), recordRow('İkinci'), recordRow('Üçüncü')];
    serve(rows);
    vi.mocked(AnalysisRecordsService.detail).mockImplementation(async (id) => recordDetail(rows.find((r) => r.public_id === id)!));
    await openPage();
    fireEvent.click(bodyRows()[0]);
    expect(await screen.findByRole('dialog', {name: 'Birinci'})).toBeInTheDocument();
    expect(where()).toBe(`/admin/analizler/${rows[0].public_id}`);

    fireEvent.keyDown(drawer(), {key: 'ArrowUp'});
    expect(where()).toBe(`/admin/analizler/${rows[0].public_id}`);
    fireEvent.keyDown(drawer(), {key: 'ArrowDown'});
    expect(await screen.findByRole('dialog', {name: 'İkinci'})).toBeInTheDocument();
    fireEvent.keyDown(drawer(), {key: 'ArrowDown'});
    expect(await screen.findByRole('dialog', {name: 'Üçüncü'})).toBeInTheDocument();
    fireEvent.keyDown(drawer(), {key: 'ArrowDown'});
    expect(where()).toBe(`/admin/analizler/${rows[2].public_id}`);
    fireEvent.keyDown(drawer(), {key: 'ArrowUp'});
    expect(await screen.findByRole('dialog', {name: 'İkinci'})).toBeInTheDocument();

    fireEvent.keyDown(document, {key: 'Escape'});
    await waitFor(() => expect(where()).toBe('/admin/analizler'));
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.keyDown(bodyRows()[2], {key: 'Enter'});
    expect(await screen.findByRole('dialog', {name: 'Üçüncü'})).toBeInTheDocument();
    fireEvent.keyDown(document, {key: 'Escape'});
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.keyDown(bodyRows()[1], {key: ' '});
    expect(await screen.findByRole('dialog', {name: 'İkinci'})).toBeInTheDocument();
    // A record read once is not read again.
    expect(vi.mocked(AnalysisRecordsService.detail).mock.calls.filter(([id]) => id === rows[1].public_id)).toHaveLength(1);
  });

  it('says why a deep-linked record cannot be shown', async () => {
    await openPage('/admin/analizler/0b6f6f3e-3e0a-4c58-9a3a-8a2f9c1e2d11');
    const panel = await screen.findByRole('dialog', {name: message('records.detail.title')});
    expect(await within(panel).findByText(message('admin.error.analysis_record_not_found'))).toHaveClass('msg', 'bad');
  });

  it('shows the filter\'s performance and filters by a person clicked there', async () => {
    serve([recordRow('Mevduat')]);
    vi.mocked(AnalysisRecordsService.summary).mockResolvedValue(
      recordSummary({
        count: 12,
        p50_ms: 4500,
        p90_ms: 30000,
        max_ms: 125000,
        llm_calls: 30,
        prompt_tokens: 1234567,
        completion_tokens: 950,
        phases: [
          {phase: 'queue', average_ms: null, count: 0},
          {phase: 'model_check', average_ms: 400, count: 12},
          {phase: 'analyst_pick', average_ms: 4000, count: 10},
        ],
        askers: [
          {...AYSE, count: 8},
          {...ALI, count: 4},
        ],
      }),
    );
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.performance')}));
    const panel = screen.getByRole('dialog', {name: message('records.perf.title')});
    expect(panel).toHaveTextContent(message('records.perf.sub', {period: message('records.periodName.7d'), count: 12}));
    const bars = [...panel.querySelectorAll<HTMLElement>('.hbars .tr')];
    expect(bars.map((bar) => [bar.title, bar.querySelector('i')?.style.width])).toEqual([
      [message('records.perf.phaseCount', {count: 12}), '10.0%'],
      [message('records.perf.phaseCount', {count: 10}), '100.0%'],
    ]);
    expect(panel).toHaveTextContent(message('records.perf.spread', {p50: '4,5 sn', p90: '30 sn', max: '2 dk 05 sn'}));
    expect(panel).toHaveTextContent(message('records.perf.usageValue', {calls: 30, prompt: '1,2 M', completion: '950'}));
    fireEvent.click(within(panel).getByText('Ayşe Kaya'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByRole('combobox', {name: message('records.asker.label')})).toHaveValue(AYSE.public_id);
    await waitFor(() => expect(list()).toHaveBeenLastCalledWith({...NO_FILTER, asked_by: AYSE.public_id}, 1));
  });

  it('says when the filter has nothing for the performance drawer', async () => {
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.performance')}));
    expect(within(drawer()).getByText(message('records.perf.empty'))).toBeInTheDocument();
  });

  it('opens the performance drawer and a recent question from the command palette', async () => {
    const row = recordRow('Kredi kartı limiti', {verdict: null, flow: 'unavailable'});
    serve([row]);
    vi.mocked(AnalysisRecordsService.detail).mockResolvedValue(recordDetail(row));
    renderApp('/admin/genel');
    await screen.findByText(message('overview.week.title'));
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    const box = await screen.findByRole('textbox', {name: message('admin.palette.label')});
    fireEvent.change(box, {target: {value: 'performans'}});
    fireEvent.click(screen.getByText(message('admin.palette.performance'), {selector: '.pi div'}));
    expect(await screen.findByRole('dialog', {name: message('records.perf.title')})).toBeInTheDocument();
    expect(where()).toBe('/admin/analizler');
    fireEvent.keyDown(document, {key: 'Escape'});

    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    fireEvent.change(await screen.findByRole('textbox', {name: message('admin.palette.label')}), {target: {value: 'kredi'}});
    const item = await screen.findByText('Kredi kartı limiti', {selector: '.pi div'});
    expect(item.parentElement?.querySelector('small')).toHaveTextContent(/ · Yapılamadı$/);
    expect(screen.getByText(message('admin.palette.recent'))).toBeInTheDocument();
    expect(list()).toHaveBeenCalledWith({period: 'all'}, 1, undefined, 200);
    fireEvent.click(item);
    expect(await screen.findByRole('dialog', {name: 'Kredi kartı limiti'})).toBeInTheDocument();
    expect(where()).toBe(`/admin/analizler/${row.public_id}`);
  });

  it('tells there is nothing to delete for an empty filter', async () => {
    const remove = vi.spyOn(AnalysisRecordsService, 'remove');
    const confirm = answerConfirm(true);
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(await screen.findByText(message('records.clear.nothing'))).toBeInTheDocument();
    expect(screen.getByText(message('records.clear.nothingLine'))).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it('deletes the filter\'s records before until after the confirmation, then the kept answers on a second yes', async () => {
    serve([recordRow('Mevduat')], 12);
    const remove = vi.spyOn(AnalysisRecordsService, 'remove').mockResolvedValue({deleted_count: 12, remaining_count: 30});
    const clearAnswers = vi.spyOn(SavedAnswersService, 'clear').mockResolvedValue({removed: 7});
    await openPage();
    fireEvent.change(screen.getByRole('combobox', {name: message('records.flowFilter.label')}), {target: {value: 'failed'}});
    await waitFor(() => expect(list()).toHaveBeenLastCalledWith({...NO_FILTER, flow: 'failed'}, 1));
    await waitFor(() => expect(title()).toBe(message('records.list.title', {period: message('records.periodName.7d'), count: 12})));

    const confirm = answerConfirm(false);
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(confirm).toHaveBeenCalledWith(message('records.clear.confirmFiltered', {count: 12, period: 'son 7 gün'}));
    expect(message('records.clear.confirmFiltered')).toContain(
      '\n\nSilinen analizler kalıcı olarak silinir, yedek tutulmaz. Kullanıcılar bu analizlerin sonucunu ve raporunu da açamaz.',
    );
    expect(remove).not.toHaveBeenCalled();

    const twice = answerConfirm(true, true);
    list().mockClear();
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(await screen.findByText(message('records.clear.done'))).toBeInTheDocument();
    expect(screen.getByText(message('records.clear.doneLine', {deleted: 12, remaining: 30}))).toBeInTheDocument();
    expect(remove).toHaveBeenCalledWith(SNAPSHOT_AT, {filters: {...NO_FILTER, flow: 'failed'}});
    expect(twice).toHaveBeenLastCalledWith(message('records.clear.answersConfirm'));
    expect(await screen.findByText(message('maintenance.answers.cleared'))).toBeInTheDocument();
    expect(screen.getByText(message('maintenance.answers.clearedLine', {count: 7}))).toBeInTheDocument();
    expect(clearAnswers).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(list()).toHaveBeenCalledWith({...NO_FILTER, flow: 'failed'}, 1));
  });

  it('deletes every record with all=true for "Tümü" without other filters and asks about the period otherwise', async () => {
    serve([recordRow('Mevduat')], 40);
    const remove = vi.spyOn(AnalysisRecordsService, 'remove').mockResolvedValue({deleted_count: 40, remaining_count: 0});
    const clearAnswers = vi.spyOn(SavedAnswersService, 'clear');
    await openPage();
    const period = answerConfirm(false);
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(period).toHaveBeenCalledWith(message('records.clear.confirmPeriod', {count: 40, period: 'son 7 gün'}));

    fireEvent.click(screen.getByRole('button', {name: message('records.period.all')}));
    await waitFor(() => expect(title()).toBe(message('records.list.title', {period: message('records.periodName.all'), count: 40})));
    const all = answerConfirm(true, false);
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(all).toHaveBeenCalledWith(message('records.clear.confirmAll', {count: 40}));
    expect(await screen.findByText(message('records.clear.done'))).toBeInTheDocument();
    expect(remove).toHaveBeenCalledWith(SNAPSHOT_AT, {all: true});
    expect(clearAnswers).not.toHaveBeenCalled();
  });

  it('reports a failed deletion', async () => {
    serve([recordRow('Mevduat')]);
    vi.spyOn(AnalysisRecordsService, 'remove').mockRejectedValue(new ApiError(422, 'x', 'analysis_delete_scope_missing'));
    answerConfirm(true);
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('records.clear')}));
    expect(await screen.findByText(message('records.clear.failed'))).toBeInTheDocument();
    expect(screen.getByText(message('admin.error.analysis_delete_scope_missing'))).toBeInTheDocument();
  });
});
