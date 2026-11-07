import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {formatDateTime, formatWhen} from '@/lib/format';
import {AnalysisRecordsService} from '@/services/analysisRecords';
import {DictionaryService} from '@/services/dictionary';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {SavedAnswersService} from '@/services/savedAnswers';
import {SearchSettingsService} from '@/services/searchSettings';
import {dictionaryState, EMPTY_DICTIONARY, indexState, recordPage, recordRow, recordSummary} from '@/test/admin';
import {integration, llmState} from '@/test/llm';
import {message, renderApp, signedIn} from '@/test/render';

const t = (key: string, values?: Record<string, string | number>) => message(key, values);

/** The health card with this title. */
const card = (title: string) => screen.getByText(title, {selector: '.hc .k'}).closest('.hc') as HTMLElement;
const value = (title: string) => card(title).querySelector('.v')?.textContent;
const line = (title: string) => card(title).querySelector('.s')?.textContent;

function connected(state: 'ok' | 'down' = 'ok') {
  const item = integration('Kurum vLLM', {active: true, chat_model: 'org/qwen-32b'});
  const answer = llmState([item]);
  if (state === 'down') answer.model_state = {...answer.model_state, state: 'down', reason: 'Model sunucusuna ulaşılamadı: bağlantı kurulamadı', code: 'connect_error'};
  vi.mocked(LlmIntegrationService.list).mockResolvedValue(answer);
}

async function openPage() {
  renderApp('/admin/genel');
  return screen.findByText(message('overview.week.title'));
}

describe('Genel bakış page (analysis-records Requirement 13-15)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows four healthy cards and no first-run card when every step is done', async () => {
    connected();
    vi.mocked(DictionaryService.state).mockResolvedValue(dictionaryState());
    vi.mocked(SearchSettingsService.index).mockResolvedValue(indexState());
    vi.mocked(SavedAnswersService.summary).mockResolvedValue({total: 1200, usable: 800, newest_at: null});
    vi.mocked(AnalysisRecordsService.list).mockResolvedValue(recordPage({items: [recordRow('Müşteri sayısı')], total: 1}));
    await openPage();
    await waitFor(() => expect(value(message('overview.index.title'))).toBe(message('overview.index.ok')));

    expect(screen.getByText(message('admin.page.genel.description'))).toBeInTheDocument();
    expect(card(message('overview.model.title'))).toHaveClass('hc', 'ok');
    expect(value(message('overview.model.title'))).toBe('qwen-32b');
    expect(line(message('overview.model.title'))).toBe(message('overview.model.ok', {detail: message('ai.status.via', {name: 'Kurum vLLM'})}));
    expect(within(card(message('overview.model.title'))).getByRole('link', {name: message('overview.model.connections')})).toHaveAttribute('href', '/admin/yapay-zeka');

    expect(card(message('overview.dictionary.title'))).toHaveClass('ok');
    expect(value(message('overview.dictionary.title'))).toBe(message('overview.dictionary.value', {count: 12}));
    expect(line(message('overview.dictionary.title'))).toBe(
      message('overview.dictionary.line', {columns: 120, source: 'sozluk_sentetik.xlsx', at: formatDateTime('2026-10-08T09:00:00Z')}),
    );
    expect(within(card(message('overview.dictionary.title'))).getByRole('link', {name: message('overview.dictionary.open')})).toHaveAttribute('href', '/admin/sozluk');

    expect(card(message('overview.index.title'))).toHaveClass('ok');
    expect(line(message('overview.index.title'))).toBe(message('overview.index.built', {when: formatWhen('2026-10-08T09:00:00Z', t)}));
    expect(within(card(message('overview.index.title'))).queryByRole('button')).toBeNull();

    expect(card(message('overview.answers.title'))).toHaveClass('ok');
    expect(value(message('overview.answers.title'))).toBe(message('overview.answers.value', {count: 800}));
    expect(line(message('overview.answers.title'))).toBe(message('overview.answers.line', {total: '1.200'}));
    expect(within(card(message('overview.answers.title'))).getByRole('link', {name: message('overview.answers.manage')})).toHaveAttribute('href', '/admin/bakim');

    expect(screen.queryByText(message('overview.setup.title'))).toBeNull();
  });

  it('shows the warning states, the changed inputs and the first-run steps left', async () => {
    connected('down');
    vi.mocked(DictionaryService.state).mockResolvedValue(dictionaryState({}, 'older-1'));
    vi.mocked(SearchSettingsService.index).mockResolvedValue(indexState({state: 'stale', stale_inputs: ['dictionary', 'terms']}));
    const rebuild = vi.spyOn(SearchSettingsService, 'rebuild').mockResolvedValue({...indexState(), elapsed_ms: 10});
    await openPage();
    await waitFor(() => expect(value(message('overview.index.title'))).toBe(message('overview.index.stale')));

    expect(card(message('overview.model.title'))).toHaveClass('bad');
    expect(line(message('overview.model.title'))).toBe(message('overview.model.down', {reason: 'Model sunucusuna ulaşılamadı: bağlantı kurulamadı'}));
    expect(within(card(message('overview.model.title'))).getByRole('link', {name: message('overview.model.connect')})).toBeInTheDocument();
    expect(card(message('overview.dictionary.title'))).toHaveClass('warn');
    expect(card(message('overview.index.title'))).toHaveClass('warn');
    expect(line(message('overview.index.title'))).toBe(message('overview.index.changed', {inputs: 'sözlük, terim sözlüğü'}));
    expect(card(message('overview.answers.title'))).not.toHaveClass('ok');
    expect(value(message('overview.answers.title'))).toBe(message('overview.answers.value', {count: 0}));
    expect(line(message('overview.answers.title'))).toBe(message('overview.answers.none'));

    // Steps: the dictionary is there; the model does not answer; nothing was asked yet.
    const setup = screen.getByText(message('overview.setup.title')).closest('section') as HTMLElement;
    expect(within(setup).getByText(message('overview.setup.progress', {done: 1}))).toBeInTheDocument();
    const steps = within(setup).getAllByRole('listitem');
    expect(steps[0]).toHaveClass('done');
    expect(within(steps[0]).queryByRole('link')).toBeNull();
    expect(within(steps[1]).getByRole('link', {name: message('overview.setup.go')})).toHaveAttribute('href', '/admin/yapay-zeka');
    expect(within(steps[2]).getByRole('link', {name: message('overview.setup.go')})).toHaveAttribute('href', '/');

    vi.mocked(SearchSettingsService.index).mockResolvedValue(indexState());
    fireEvent.click(within(card(message('overview.index.title'))).getByRole('button', {name: message('overview.index.rebuild')}));
    expect(await screen.findByText(message('admin.index.rebuilt'))).toBeInTheDocument();
    expect(rebuild).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(value(message('overview.index.title'))).toBe(message('overview.index.ok')));
  });

  it('shows a missing dictionary and model, an empty and a building index', async () => {
    vi.mocked(DictionaryService.state).mockResolvedValue(EMPTY_DICTIONARY);
    await openPage();
    await waitFor(() => expect(value(message('overview.index.title'))).toBe(message('overview.index.empty')));
    expect(value(message('overview.model.title'))).toBe(message('overview.model.none'));
    expect(card(message('overview.model.title'))).toHaveClass('warn');
    expect(line(message('overview.model.title'))).toBe(message('overview.model.noneLine'));
    expect(value(message('overview.dictionary.title'))).toBe(message('overview.dictionary.none'));
    expect(line(message('overview.dictionary.title'))).toBe(message('overview.dictionary.noneLine'));
    expect(within(card(message('overview.dictionary.title'))).getByRole('link', {name: message('overview.dictionary.connect')})).toBeInTheDocument();
    expect(line(message('overview.index.title'))).toBe(message('overview.index.emptyLine'));
    const setup = screen.getByText(message('overview.setup.title')).closest('section') as HTMLElement;
    expect(within(setup).getByText(message('overview.setup.progress', {done: 0}))).toBeInTheDocument();
    expect(within(within(setup).getAllByRole('listitem')[0]).getByRole('link')).toHaveAttribute('href', '/admin/sozluk');
  });

  it('names a building index', async () => {
    vi.mocked(SearchSettingsService.index).mockResolvedValue(indexState({state: 'building'}));
    await openPage();
    await waitFor(() => expect(value(message('overview.index.title'))).toBe(message('overview.index.building')));
    expect(card(message('overview.index.title'))).toHaveClass('warn');
  });

  it('shows "…" on the card whose source cannot be read and keeps the others', async () => {
    connected();
    vi.mocked(SavedAnswersService.summary).mockRejectedValue(new ApiError(500, 'x'));
    vi.mocked(DictionaryService.state).mockRejectedValue(new ApiError(500, 'x'));
    await openPage();
    await waitFor(() => expect(value(message('overview.model.title'))).toBe('qwen-32b'));
    expect(value(message('overview.answers.title'))).toBe(message('overview.unknown'));
    expect(value(message('overview.dictionary.title'))).toBe(message('overview.unknown'));
    expect(screen.getByText(message('overview.recent.empty'))).toBeInTheDocument();
  });

  it('reads "–" for indicators without a denominator and the week\'s figures otherwise', async () => {
    await openPage();
    const tiles = () => [...document.querySelectorAll('#p-genel .kpis .kpi')].map((tile) => [tile.querySelector('.v')?.textContent, tile.querySelector('.s')?.textContent]);
    expect(tiles()).toEqual([
      ['0', message('records.kpi.none')],
      [message('records.kpi.blank'), message('records.kpi.none')],
      [message('records.kpi.blank'), message('records.kpi.analystAll')],
      [message('records.kpi.blank'), message('records.kpi.typicalNone')],
    ]);
    expect(AnalysisRecordsService.summary).toHaveBeenCalledWith({period: '7d'});
  });

  it('computes the week\'s indicators from the summary', async () => {
    vi.mocked(AnalysisRecordsService.summary).mockResolvedValue(
      recordSummary({
        count: 10,
        newest_at: '2026-10-08T09:00:00Z',
        with_result: 8,
        with_tables: 6,
        flows: {analyst: 6, reused: 1, unavailable: 1, cancelled: 1, failed: 0, interrupted: 1},
        analyst_p50_ms: 4500,
        analyst_p90_ms: 125000,
      }),
    );
    await openPage();
    const tiles = [...document.querySelectorAll('#p-genel .kpis .kpi')].map((tile) => [tile.querySelector('.v')?.textContent, tile.querySelector('.s')?.textContent]);
    expect(tiles).toEqual([
      ['10', message('records.kpi.questionsLast', {when: formatWhen('2026-10-08T09:00:00Z', t)})],
      ['%75', message('records.kpi.tablesLine', {found: 6, answered: 8})],
      ['%70', message('records.kpi.analystFailed', {count: 2})],
      ['4,5 sn', message('records.kpi.typicalP90', {duration: '2 dk 05 sn'})],
    ]);
  });

  it('draws 14 days with a tooltip per day and a date label every second day', async () => {
    const days = Array.from({length: 14}, (_, i) => ({
      date: new Date(Date.UTC(2026, 8, 25 + i)).toISOString().slice(0, 10),
      with_tables: i,
      without_tables: i % 3,
    }));
    vi.mocked(AnalysisRecordsService.dailyCounts).mockResolvedValue({days});
    await openPage();
    const chart = screen.getByRole('img', {name: message('overview.chart.label')});
    // The day as the source wrote it: the browser's Turkish day and month (toLocaleDateString).
    const label = (day: number) => new Date(2026, 8, day).toLocaleDateString('tr-TR', {day: '2-digit', month: '2-digit'});
    const titles = [...chart.querySelectorAll('title')].map((title) => title.textContent);
    expect(titles).toHaveLength(14);
    expect(titles[0]).toBe(message('overview.chart.tip', {date: label(25), total: 0, ok: 0, no: 0}));
    expect(titles[13]).toBe(message('overview.chart.tip', {date: label(38), total: 14, ok: 13, no: 1}));
    expect([...chart.querySelectorAll('text')].map((text) => text.textContent)).toEqual([26, 28, 30, 32, 34, 36, 38].map(label));
    // Each day's two bars stand on the base line; the taller day reaches the top margin.
    const last = chart.querySelectorAll('g')[13];
    expect(Number(last.querySelector('.bar-ok')?.getAttribute('height')) + Number(last.querySelector('.bar-no')?.getAttribute('height'))).toBeCloseTo(124);
    expect(AnalysisRecordsService.dailyCounts).toHaveBeenCalledWith(14);
  });

  it('lists the newest questions as links to their record', async () => {
    const first = recordRow('Şube bazında mevduat', {verdict: 'KISMEN VAR', flow: 'reused'});
    const second = recordRow('İptal edilen soru', {verdict: null, flow: 'cancelled'});
    vi.mocked(AnalysisRecordsService.list).mockResolvedValue(recordPage({items: [first, second], total: 2}));
    await openPage();
    const recent = screen.getByText(message('overview.recent.title')).closest('section') as HTMLElement;
    const links = within(recent).getAllByRole('link');
    expect(links[0]).toHaveAttribute('href', `/admin/analizler/${first.public_id}`);
    expect(links[0].querySelector('.vb')).toHaveClass('vb', 'KISMEN');
    expect(links[0].querySelector('.flow')).toHaveClass('flow', 'önbellek');
    expect(links[0].querySelector('.flow')).toHaveTextContent('↻ Önceki cevap');
    expect(links[0].querySelector('.q')).toHaveAttribute('title', 'Şube bazında mevduat');
    expect(links[1].querySelector('.vb')).toHaveTextContent(message('records.verdict.stopped'));
    expect(AnalysisRecordsService.list).toHaveBeenCalledWith({period: 'all'}, 1, undefined, 100);
    fireEvent.click(links[0]);
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe(`/admin/analizler/${first.public_id}`));
  });
});
