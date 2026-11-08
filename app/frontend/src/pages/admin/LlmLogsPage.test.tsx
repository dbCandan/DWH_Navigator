import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {clearAuth} from '@/lib/authStorage';
import {setConfirmHandler} from '@/lib/confirm';
import {prettyJson, replyText, requestMessages} from '@/lib/llmCallBody';
import {DictionaryService} from '@/services/dictionary';
import {LlmCallLogService} from '@/services/llmCallLogs';
import {answerConfirm, dictionaryState} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {LlmCallDetail, LlmCallRow} from '@/types/llmCallLogs';

const UNTIL = '2026-11-07T09:05:00Z';

const row: LlmCallRow = {
  public_id: '0b6f6f3e-3e0a-4c58-9a3a-8a2f9c1e2d11',
  purpose: 'analysis',
  outcome: 'ok',
  model: 'gemma-4-31b',
  integration_public_id: null,
  analysis_public_id: null,
  started_at: '2026-11-07T09:00:00Z',
  wait_ms: 0,
  duration_ms: 1200,
  http_status: 200,
  requests: 1,
  repaired: false,
  prompt_tokens: 120,
  completion_tokens: 30,
};

const detail: LlmCallDetail = {
  ...row,
  adaptations: [],
  exchanges: [
    {
      request: JSON.stringify({messages: [{role: 'system', content: 'Sistem talimatı'}, {role: 'user', content: 'Şube sorusu'}]}),
      request_truncated: false,
      status: 200,
      response: JSON.stringify({choices: [{message: {content: '{"cevap":"Ankara"}'}}]}),
      response_truncated: false,
      duration_ms: 1100,
    },
  ],
};

describe('LLM kayıtları page', () => {
  beforeEach(() => {
    signedIn('manager');
    vi.mocked(DictionaryService.state).mockResolvedValue(dictionaryState());
    vi.mocked(DictionaryService.tables).mockResolvedValue([]);
    vi.spyOn(LlmCallLogService, 'list').mockResolvedValue({rows: [row], total: 1, retention_days: 7, until: UNTIL});
    vi.spyOn(LlmCallLogService, 'read').mockResolvedValue(detail);
  });
  afterEach(() => {
    setConfirmHandler(null);
    vi.restoreAllMocks();
    clearAuth();
  });

  it('lists the calls and opens what was sent and what came back', async () => {
    renderApp('/admin/llm-kayitlari');
    fireEvent.click(await screen.findByText('gemma-4-31b'));
    const drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByText('Sistem talimatı')).toBeInTheDocument();
    expect(within(drawer).getByText('Şube sorusu')).toBeInTheDocument();
    expect(within(drawer).getByText(/"cevap": "Ankara"/)).toBeInTheDocument();
    expect(LlmCallLogService.read).toHaveBeenCalledWith(row.public_id);
  });

  it('names the outcome in words and leads from an analysis call to its analysis', async () => {
    const analysisId = '7d1c1f0e-5b0a-4e7b-9a55-0c9d2f6b3a10';
    vi.mocked(LlmCallLogService.list).mockResolvedValue({
      rows: [row, {...row, public_id: 'f1', outcome: 'timeout', model: 'other-model'}],
      total: 2,
      retention_days: 7,
      until: UNTIL,
    });
    vi.mocked(LlmCallLogService.read).mockResolvedValue({...detail, analysis_public_id: analysisId});
    renderApp('/admin/llm-kayitlari');
    await screen.findByText('other-model');
    const pills = [...document.querySelectorAll('tbody .pill')];
    expect(pills.map((pill) => pill.textContent)).toEqual([message('llmLogs.outcome.ok'), message('llmLogs.outcome.timeout')]);
    expect(pills[1]).toHaveClass('pill', 'bad');
    expect(pills[1]).toHaveAttribute('title', 'timeout');
    const filter = screen.getByRole('combobox', {name: message('llmLogs.outcomeFilter')});
    expect(within(filter).getByRole('option', {name: message('llmLogs.outcome.invalid_json')})).toHaveValue('invalid_json');
    fireEvent.click(screen.getByText('gemma-4-31b'));
    const drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByRole('link', {name: message('llmLogs.detail.openAnalysis')})).toHaveAttribute(
      'href',
      `/admin/analizler/${analysisId}`,
    );
  });

  it('shows only the calls of one analysis from ?analiz= and lets the filter go', async () => {
    const analysisId = '7d1c1f0e-5b0a-4e7b-9a55-0c9d2f6b3a10';
    renderApp(`/admin/llm-kayitlari?analiz=${analysisId}`);
    await waitFor(() => expect(LlmCallLogService.list).toHaveBeenLastCalledWith(expect.objectContaining({analysis: analysisId})));
    expect(screen.getByText(message('llmLogs.analysisFilter'))).toBeInTheDocument();
    const note = screen.getByText(message('llmLogs.analysisFilter')).closest('.msg') as HTMLElement;
    expect(within(note).getByRole('link', {name: message('llmLogs.detail.openAnalysis')})).toHaveAttribute('href', `/admin/analizler/${analysisId}`);
    fireEvent.click(within(note).getByRole('button', {name: message('llmLogs.analysisFilterClear')}));
    await waitFor(() => expect(LlmCallLogService.list).toHaveBeenLastCalledWith(expect.objectContaining({analysis: ''})));
    expect(screen.queryByText(message('llmLogs.analysisFilter'))).toBeNull();
  });

  it('reads again with the chosen filter', async () => {
    renderApp('/admin/llm-kayitlari');
    fireEvent.change(await screen.findByRole('combobox', {name: message('llmLogs.purposeFilter')}), {target: {value: 'dictionary_sync'}});
    await waitFor(() => expect(LlmCallLogService.list).toHaveBeenLastCalledWith(expect.objectContaining({purpose: 'dictionary_sync'})));
  });

  it('says so when nothing was called yet', async () => {
    vi.mocked(LlmCallLogService.list).mockResolvedValue({rows: [], total: 0, retention_days: 7, until: UNTIL});
    renderApp('/admin/llm-kayitlari');
    expect(await screen.findByText(message('llmLogs.empty.none'))).toBeInTheDocument();
  });
});

describe('deleting LLM kayıtları', () => {
  const page = {rows: [row, {...row, public_id: 'f1', model: 'other-model'}], total: 2, retention_days: 7, until: UNTIL};

  beforeEach(() => {
    signedIn('manager');
    vi.mocked(DictionaryService.state).mockResolvedValue(dictionaryState());
    vi.mocked(DictionaryService.tables).mockResolvedValue([]);
    vi.spyOn(LlmCallLogService, 'list').mockResolvedValue(page);
  });
  afterEach(() => {
    setConfirmHandler(null);
    vi.restoreAllMocks();
    clearAuth();
  });

  it('asks on the page how many calls go, deletes them all on yes, reads again and tells', async () => {
    const remove = vi.spyOn(LlmCallLogService, 'remove').mockResolvedValue({deleted_count: 2, remaining_count: 0});
    const confirm = vi.fn(() => true);
    Object.defineProperty(window, 'confirm', {value: confirm, configurable: true, writable: true});
    renderApp('/admin/llm-kayitlari');
    await screen.findByText('other-model');

    fireEvent.click(screen.getByRole('button', {name: message('llmLogs.clear')}));
    const dialog = await screen.findByRole('alertdialog');
    const [question, , warning] = message('llmLogs.clear.confirmAll', {count: 2}).split('\n');
    expect(within(dialog).getByRole('heading', {name: question})).toBeInTheDocument();
    expect(within(dialog).getByText(warning!)).toBeInTheDocument();
    expect(warning).toContain('geri alınamaz');
    expect(within(dialog).getByRole('button', {name: message('admin.confirm.cancel')})).toHaveFocus();
    fireEvent.click(within(dialog).getByRole('button', {name: message('admin.confirm.cancel')}));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(remove).not.toHaveBeenCalled();

    vi.mocked(LlmCallLogService.list).mockClear();
    vi.mocked(LlmCallLogService.list).mockResolvedValue({rows: [], total: 0, retention_days: 7, until: UNTIL});
    fireEvent.click(screen.getByRole('button', {name: message('llmLogs.clear')}));
    fireEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {name: message('llmLogs.clear.confirmAction')}),
    );
    expect(await screen.findByText(message('llmLogs.clear.done'))).toBeInTheDocument();
    expect(screen.getByText(message('llmLogs.clear.doneLine', {deleted: 2, remaining: 0}))).toBeInTheDocument();
    expect(remove).toHaveBeenCalledWith(UNTIL, {all: true});
    expect(await screen.findByText(message('llmLogs.empty.none'))).toBeInTheDocument();
    expect(LlmCallLogService.list).toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });

  it('deletes only what the filter shows', async () => {
    const remove = vi.spyOn(LlmCallLogService, 'remove').mockResolvedValue({deleted_count: 2, remaining_count: 5});
    const confirm = answerConfirm(true);
    renderApp('/admin/llm-kayitlari');
    fireEvent.change(await screen.findByRole('combobox', {name: message('llmLogs.outcomeFilter')}), {
      target: {value: 'timeout'},
    });
    await waitFor(() =>
      expect(LlmCallLogService.list).toHaveBeenLastCalledWith(expect.objectContaining({outcome: 'timeout'})),
    );
    await screen.findByText('other-model');
    fireEvent.click(screen.getByRole('button', {name: message('llmLogs.clear')}));
    expect(await screen.findByText(message('llmLogs.clear.done'))).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledWith(message('llmLogs.clear.confirmFiltered', {count: 2}));
    expect(remove).toHaveBeenCalledWith(UNTIL, {filters: {purpose: '', outcome: 'timeout', q: '', analysis: ''}});
  });

  it('tells there is nothing to delete for an empty list', async () => {
    vi.mocked(LlmCallLogService.list).mockResolvedValue({rows: [], total: 0, retention_days: 7, until: UNTIL});
    const remove = vi.spyOn(LlmCallLogService, 'remove');
    const confirm = answerConfirm(true);
    renderApp('/admin/llm-kayitlari');
    await screen.findByText(message('llmLogs.empty.none'));
    fireEvent.click(screen.getByRole('button', {name: message('llmLogs.clear')}));
    expect(await screen.findByText(message('llmLogs.clear.nothing'))).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it('reports a refused deletion and keeps the list', async () => {
    vi.spyOn(LlmCallLogService, 'remove').mockRejectedValue(new ApiError(403, 'x', 'forbidden'));
    answerConfirm(true);
    renderApp('/admin/llm-kayitlari');
    await screen.findByText('other-model');
    fireEvent.click(screen.getByRole('button', {name: message('llmLogs.clear')}));
    expect(await screen.findByText(message('llmLogs.clear.failed'))).toBeInTheDocument();
    expect(screen.getByText('other-model')).toBeInTheDocument();
  });
});

describe('logged bodies', () => {
  it('reads messages and the reply, and leaves a cut body as it is', () => {
    expect(requestMessages(detail.exchanges[0]!.request)).toHaveLength(2);
    expect(replyText(detail.exchanges[0]!.response)).toContain('"cevap": "Ankara"');
    expect(requestMessages('{"messages": [{"ro')).toEqual([]);
    expect(replyText('<html>502</html>')).toBeNull();
    expect(prettyJson('{"a"')).toBe('{"a"');
  });
});
