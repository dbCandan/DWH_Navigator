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
