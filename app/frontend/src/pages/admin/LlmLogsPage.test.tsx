import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth} from '@/lib/authStorage';
import {prettyJson, replyText, requestMessages} from '@/lib/llmCallBody';
import {DictionaryService} from '@/services/dictionary';
import {LlmCallLogService} from '@/services/llmCallLogs';
import {dictionaryState} from '@/test/admin';
import {message, renderApp, signedIn} from '@/test/render';
import type {LlmCallDetail, LlmCallRow} from '@/types/llmCallLogs';

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
    vi.spyOn(LlmCallLogService, 'list').mockResolvedValue({rows: [row], total: 1, retention_days: 7});
    vi.spyOn(LlmCallLogService, 'read').mockResolvedValue(detail);
  });
  afterEach(() => {
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
    vi.mocked(LlmCallLogService.list).mockResolvedValue({rows: [], total: 0, retention_days: 7});
    renderApp('/admin/llm-kayitlari');
    expect(await screen.findByText(message('llmLogs.empty.none'))).toBeInTheDocument();
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
