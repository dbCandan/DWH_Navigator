import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '@/lib/apiClient';
import {setConfirmHandler} from '@/lib/confirm';
import {clearAuth} from '@/lib/authStorage';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import {integration, llmState} from '@/test/llm';
import {message, renderApp, signedIn} from '@/test/render';
import type {LlmIntegrationItem, LlmIntegrationsState, LlmModelRow} from '@/types/llm';

const SPARK = integration('DGX Spark 1', {
  active: true,
  chat_model: 'google/gemma-4-31b',
  has_key: true,
  last_test: {at: new Date().toISOString(), ok: true, summary: 'Sunucu: ✓; Sohbet modeli: ✓'},
});
const STUDIO = integration('LM Studio', {endpoint: 'http://10.0.0.9:1234/v1'});
const BOTH = llmState([SPARK, STUDIO]);

const model = (id: string, overrides: Partial<LlmModelRow> = {}): LlmModelRow => ({
  id,
  type: 'llm',
  loaded: null,
  context: null,
  owner: '',
  quant: '',
  in_use: false,
  ...overrides,
});

/** The browser's confirmation dialog, answered by the test. */
function answerConfirm(...answers: boolean[]) {
  const confirm = vi.fn<(text: string) => boolean>(() => (answers.length > 1 ? (answers.shift() as boolean) : answers[0]));
  Object.defineProperty(window, 'confirm', {value: confirm, configurable: true, writable: true});
  setConfirmHandler((text) => confirm(text));
  return confirm;
}

function serve(state: LlmIntegrationsState) {
  return vi.spyOn(LlmIntegrationService, 'list').mockResolvedValue(state);
}

async function openPage(state: LlmIntegrationsState = BOTH, path = '/admin/yapay-zeka') {
  serve(state);
  renderApp(path);
  // The first render loads the admin shell's modules, which takes longer than a second in a cold container.
  await screen.findByRole('heading', {level: 2, name: message('ai.list.title', {count: state.items.length})}, {timeout: 5000});
}

const card = (name: string) => screen.getByText(name, {selector: '.integ b'}).closest('section') as HTMLElement;
const dialog = (name: string) => screen.findByRole('dialog', {name});

describe('Yapay zekâ page (llm-connection Requirement 19)', () => {
  beforeEach(() => {
    signedIn('manager');
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('shows the active chat model, the cards with their tags, the badge and the system status', async () => {
    await openPage();
    expect(screen.getByRole('heading', {level: 1, name: message('admin.page.yapay-zeka.label')})).toBeInTheDocument();
    expect(screen.getByText(message('admin.page.yapay-zeka.description'))).toBeInTheDocument();
    expect(screen.getByText(message('ai.hero.role'))).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 2, name: 'google/gemma-4-31b'})).toBeInTheDocument();
    expect(screen.getByText(message('ai.hero.ok', {name: 'DGX Spark 1'}))).toBeInTheDocument();

    const stats = [...document.querySelectorAll('.hb-stats .st')].map((node) => [node.querySelector('dt')?.textContent, node.querySelector('dd')?.textContent]);
    expect(stats.slice(0, 2)).toEqual([
      [message('ai.stat.model'), message('ai.stat.state.ok')],
      [message('ai.stat.integrations'), '2'],
    ]);
    expect(document.querySelector('.hb-stats .st')).toHaveClass('st', 'ok');
    const stage = document.querySelector('.ai-stage') as HTMLElement;
    expect(stage).toHaveClass('ok');
    expect(within(stage).getByText('DGX Spark 1')).toBeInTheDocument();
    // The generation model sits under the chat model; without its own it is the chat model.
    const generation = stage.querySelector('.ai-stage-gen') as HTMLElement;
    expect(within(generation).getByText(message('ai.hero.generationRole'))).toBeInTheDocument();
    expect(within(generation).getByText('google/gemma-4-31b')).toBeInTheDocument();
    expect(within(generation).getByText(message('ai.card.generationSame'))).toBeInTheDocument();
    expect(within(stage).getByRole('button', {name: message('ai.hero.testGeneration')})).toBeEnabled();

    const spark = card('DGX Spark 1');
    expect(spark.querySelector('.led')).toHaveClass('led', 'ok');
    expect(within(spark).getByText(message('ai.card.active'))).toHaveClass('tag', 'on');
    expect(within(spark).getByText(message('ai.card.keySaved'))).toBeInTheDocument();
    const tested = within(spark).getByText(/^✓ Test bugün/);
    expect(tested).toHaveAttribute('title', 'Sunucu: ✓; Sohbet modeli: ✓');
    expect(within(spark).getByRole('checkbox', {name: message('ai.card.deactivate')})).toBeChecked();

    const studio = card('LM Studio');
    expect(studio).toHaveClass('integ', 'off');
    expect(within(studio).getByText(message('ai.card.inactive'))).toBeInTheDocument();
    expect(within(studio).getByText(message('ai.card.noKey'))).toBeInTheDocument();
    // The chat and the generation model each show their own test.
    expect(within(studio).getAllByText(message('ai.card.untested'))).toHaveLength(2);
    expect(within(studio).getByText(message('ai.card.noModel'))).toHaveClass('msg', 'warn');

    const nav = screen.getByRole('navigation', {name: message('admin.nav.label')});
    const link = within(nav).getByRole('link', {name: message('admin.page.yapay-zeka.label')});
    expect(link.querySelector('.bdg')).toHaveClass('bdg', 'ok', 'dot');
    expect(link.querySelector('.bdg')).toHaveAttribute('title', 'gemma-4-31b');
    const status = document.getElementById('sys') as HTMLElement;
    expect(within(status).getByText('gemma-4-31b').parentElement).toHaveAttribute('title', 'DGX Spark 1 üzerinden');
  });

  it('says when no model is bound', async () => {
    await openPage(llmState([STUDIO]));
    expect(screen.getByRole('heading', {level: 2, name: message('ai.status.none')})).toBeInTheDocument();
    expect(screen.getByText(message('ai.hero.none'))).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: message('ai.test')})?.closest('.hero')).toBeFalsy();
    expect(screen.getByText(message('admin.sys.modelNone'))).toBeInTheDocument();
    expect(document.querySelector('#nav-yapay-zeka .bdg')).toHaveClass('warn');
  });

  it('says when the model does not answer', async () => {
    const reason = 'Model sunucusuna ulaşılamadı: bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı';
    await openPage(
      llmState([SPARK], {model_state: {state: 'down', model: SPARK.chat_model, code: 'connect_refused', reason, name: SPARK.name}}),
    );
    expect(screen.getByText(message('ai.hero.down', {name: 'DGX Spark 1', reason}))).toBeInTheDocument();
    expect(screen.getByText(message('admin.sys.modelDown'))).toBeInTheDocument();
    expect(document.querySelector('#nav-yapay-zeka .bdg')).toHaveClass('bad');
  });

  it('offers to add the first integration on an empty list', async () => {
    await openPage(llmState([]));
    expect(screen.getByText(message('ai.list.empty'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: message('ai.list.add')}));
    expect(await dialog(message('ai.editor.newTitle'))).toBeInTheDocument();
  });

  it('offers the fetched models in its own list: mouse, arrows, typing, a free name and Esc', async () => {
    vi.spyOn(LlmIntegrationService, 'models').mockResolvedValue({
      ok: true,
      code: null,
      message: '',
      ms: 12,
      models: [model('qwen3-8b', {context: 32768}), model('google/gemma-4-31b'), model('Qwen3-32B')],
    });
    await openPage(llmState([]));
    fireEvent.click(screen.getByRole('button', {name: message('ai.hero.new')}));
    const editor = await dialog(message('ai.editor.newTitle'));
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.endpoint')), {target: {value: 'http://10.0.0.7:1234/v1'}});
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.fetch')}));
    await within(editor).findByText(message('ai.editor.fetched', {count: 3}));

    const box = within(editor).getByRole('combobox', {name: message('ai.editor.chatModel')});
    const list = () => within(editor).queryByRole('listbox', {name: message('ai.editor.chatModelList')});
    const options = () => within(list() as HTMLElement).getAllByRole('option');
    expect(box).toHaveAttribute('aria-expanded', 'false');
    expect(list()).not.toBeInTheDocument();

    fireEvent.click(box);
    expect(box).toHaveAttribute('aria-expanded', 'true');
    expect(options()).toHaveLength(3);
    fireEvent.click(options()[1]);
    expect(box).toHaveValue('google/gemma-4-31b');
    expect(list()).not.toBeInTheDocument();

    // A chosen name does not narrow the list; typing does, in either case.
    fireEvent.click(box);
    expect(options()).toHaveLength(3);
    expect(options()[1]).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(box, {key: 'Escape'});
    fireEvent.change(box, {target: {value: 'QWEN'}});
    expect(options()).toHaveLength(2);
    fireEvent.keyDown(box, {key: 'ArrowDown'});
    fireEvent.keyDown(box, {key: 'ArrowDown'});
    expect(box).toHaveAttribute('aria-activedescendant', options()[1].id);
    fireEvent.keyDown(box, {key: 'Enter'});
    expect(box).toHaveValue('Qwen3-32B');
    expect(list()).not.toBeInTheDocument();

    // A name the server did not offer stays as typed.
    fireEvent.change(box, {target: {value: 'ozel-model'}});
    expect(box).toHaveValue('ozel-model');
    expect(list()).not.toBeInTheDocument();

    // Esc closes the open list first and the drawer only after it.
    fireEvent.change(box, {target: {value: ''}});
    expect(list()).toBeInTheDocument();
    fireEvent.keyDown(box, {key: 'Escape'});
    expect(list()).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', {name: message('ai.editor.newTitle')})).toBeInTheDocument();
    fireEvent.keyDown(box, {key: 'Escape'});
    await waitFor(() => expect(screen.queryByRole('dialog', {name: message('ai.editor.newTitle')})).not.toBeInTheDocument());
  });

  it('adds an integration: fetches the models, picks the only one, tests and saves it active', async () => {
    const models = vi
      .spyOn(LlmIntegrationService, 'models')
      .mockResolvedValue({ok: true, code: null, message: '', ms: 12, models: [model('qwen3-8b', {context: 32768})]});
    const test = vi.spyOn(LlmIntegrationService, 'test').mockResolvedValue({
      ok: true,
      steps: [
        {name: 'Sunucu', ok: true, code: null, detail: 'Bağlantı kuruldu; sunucuda 1 model var', ms: 40},
        {name: 'Sohbet modeli', ok: true, code: null, detail: 'Cevap verdi: “Ankara”', ms: 2400},
      ],
    });
    const added = integration('Yerel', {active: true, chat_model: 'qwen3-8b'});
    const create = vi.spyOn(LlmIntegrationService, 'create').mockResolvedValue({...llmState([added]), item: added});
    await openPage(llmState([]));
    fireEvent.click(screen.getByRole('button', {name: message('ai.hero.new')}));
    const editor = await dialog(message('ai.editor.newTitle'));
    expect(within(editor).getByText(message('ai.editor.sub'))).toBeInTheDocument();
    expect(within(editor).getByText(message('ai.editor.fetchFirst'))).toBeInTheDocument();
    expect(within(editor).getByText(message('ai.editor.endpointHint'))).toBeInTheDocument();
    expect(within(editor).getByLabelText(message('ai.editor.key'))).toHaveAttribute('placeholder', message('ai.editor.keyPlaceholder'));
    expect(within(editor).getByRole('checkbox', {name: message('ai.editor.activateOnSave')})).toBeChecked();

    fireEvent.change(within(editor).getByLabelText(message('ai.editor.name')), {target: {value: ' Yerel '}});
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.endpoint')), {target: {value: 'http://10.0.0.7:1234/v1'}});
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.fetch')}));
    expect(await within(editor).findByText(message('ai.editor.fetched', {count: 1}))).toBeInTheDocument();
    expect(models).toHaveBeenCalledWith({endpoint: 'http://10.0.0.7:1234/v1'});
    expect(within(editor).getByLabelText(message('ai.editor.chatModel'))).toHaveValue('qwen3-8b');
    fireEvent.click(within(editor).getByRole('combobox', {name: message('ai.editor.chatModel')}));
    expect(within(editor).getByRole('option', {name: /qwen3-8b/})).toHaveTextContent('bağlam 32.768');

    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.test')}));
    expect(await within(editor).findByText('Cevap verdi: “Ankara”')).toBeInTheDocument();
    expect(within(editor).getByText('2,4 sn')).toBeInTheDocument();
    expect(test).toHaveBeenCalledWith({
      endpoint: 'http://10.0.0.7:1234/v1',
      chat_model: 'qwen3-8b',
      temperature: 0,
      timeout_seconds: 900,
      reasoning_effort: 'none',
      seed: 42,
    });

    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.add')}));
    expect(await screen.findByText(message('ai.toast.added'))).toBeInTheDocument();
    expect(screen.getByText(message('ai.toast.savedActive', {name: 'Yerel'}))).toBeInTheDocument();
    expect(create).toHaveBeenCalledWith({
      name: 'Yerel',
      endpoint: 'http://10.0.0.7:1234/v1',
      chat_model: 'qwen3-8b',
      temperature: 0,
      timeout_seconds: 900,
      reasoning_effort: 'none',
      seed: 42,
      generation_model: '',
      generation_reasoning_effort: 'inherit',
      judge_reasoning_effort: 'inherit',
      activate: true,
      replace: false,
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(card('Yerel')).toBeInTheDocument();
  });

  it('asks for a name and an address before saving', async () => {
    const create = vi.spyOn(LlmIntegrationService, 'create');
    await openPage(llmState([]));
    fireEvent.click(screen.getByRole('button', {name: message('ai.hero.new')}));
    const editor = await dialog(message('ai.editor.newTitle'));
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.add')}));
    expect(await screen.findByText(message('ai.toast.missingLine'))).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it('shows a refused save with the server\'s fixed text and keeps the editor open', async () => {
    vi.spyOn(LlmIntegrationService, 'create').mockRejectedValue(
      new ApiError(422, 'Adres kurum ağı dışında; yalnız kurum içi model sunucusu bağlanabilir.', 'llm_endpoint_not_private'),
    );
    await openPage(llmState([]));
    fireEvent.click(screen.getByRole('button', {name: message('ai.hero.new')}));
    const editor = await dialog(message('ai.editor.newTitle'));
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.name')), {target: {value: 'Dış'}});
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.endpoint')), {target: {value: 'https://api.example.com/v1'}});
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.add')}));
    expect(await screen.findByText('Adres kurum ağı dışında; yalnız kurum içi model sunucusu bağlanabilir.')).toBeInTheDocument();
    expect(screen.getByText(message('ai.toast.saveFailed'))).toBeInTheDocument();
    expect(within(editor).getByRole('button', {name: message('ai.editor.add')})).toBeEnabled();
  });

  it('keeps a generation model beside the chat model and shows both on the card', async () => {
    vi.spyOn(LlmIntegrationService, 'models').mockResolvedValue({ok: true, code: null, message: '', ms: 3, models: []});
    const update = vi
      .spyOn(LlmIntegrationService, 'update')
      .mockImplementation(async (_item, body) => ({...BOTH, item: {...SPARK, ...body} as LlmIntegrationItem, key_cleared: false}));
    await openPage();
    expect(within(card('DGX Spark 1')).getByText(message('ai.card.generationSame'))).toBeInTheDocument();
    fireEvent.click(within(card('DGX Spark 1')).getByRole('button', {name: message('ai.card.edit')}));
    const editor = await dialog(message('ai.editor.editTitle', {name: 'DGX Spark 1'}));
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.generationModel')), {target: {value: 'qwen/qwen3.8-27b'}});
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.generationEffort')), {target: {value: 'none'}});
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.judgeEffort')), {target: {value: 'low'}});
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.save')}));
    expect(await screen.findByText(message('ai.toast.updated'))).toBeInTheDocument();
    expect(update).toHaveBeenCalledWith(
      SPARK,
      expect.objectContaining({
        chat_model: SPARK.chat_model,
        generation_model: 'qwen/qwen3.8-27b',
        generation_reasoning_effort: 'none',
        judge_reasoning_effort: 'low',
      }),
    );
  });

  it('shows the generation model on the card when one is set', async () => {
    await openPage(llmState([{...SPARK, generation_model: 'qwen/qwen3.8-27b'}]));
    expect(within(card('DGX Spark 1')).getByText('qwen/qwen3.8-27b')).toBeInTheDocument();
    expect(within(card('DGX Spark 1')).getByText(message('ai.card.generationModel'))).toBeInTheDocument();
  });

  it('tests the generation model from its card with its own reasoning and records nothing', async () => {
    const test = vi.spyOn(LlmIntegrationService, 'test').mockResolvedValue({
      ok: true,
      steps: [{name: 'Sohbet modeli', ok: true, code: null, detail: 'Cevap verdi', ms: 1800}],
    });
    await openPage(llmState([{...SPARK, generation_model: 'qwen/qwen3.8-27b', generation_reasoning_effort: 'low', judge_reasoning_effort: 'high'}]));
    const list = vi.mocked(LlmIntegrationService.list);
    const reads = list.mock.calls.length;
    const spark = card('DGX Spark 1');
    expect(within(spark).getByText('Düşünme: Düşük · Doğrulayıcı: Yüksek')).toBeInTheDocument();
    expect(within(spark).getAllByText(message('ai.card.untested'))).toHaveLength(1);
    fireEvent.click(within(spark).getByRole('button', {name: message('ai.card.testGeneration')}));
    expect(await screen.findByText(message('ai.toast.generationTestOk'))).toBeInTheDocument();
    expect(test).toHaveBeenCalledWith({public_id: SPARK.public_id, chat_model: 'qwen/qwen3.8-27b', reasoning_effort: 'low'});
    expect(within(spark).queryByText(message('ai.card.untested'))).toBeNull();
    expect(within(spark).getAllByText(/^✓ Test /)).toHaveLength(2);
    expect(list.mock.calls.length).toBe(reads);
  });

  it('tests the chat model as the generation model when none is set, with the chat reasoning when it inherits', async () => {
    const test = vi.spyOn(LlmIntegrationService, 'test').mockResolvedValue({
      ok: false,
      steps: [{name: 'Sohbet modeli', ok: false, code: 'timeout', detail: 'Zaman aşımı', ms: 900000}],
    });
    await openPage(llmState([{...SPARK, reasoning_effort: 'medium'}]));
    fireEvent.click(within(card('DGX Spark 1')).getByRole('button', {name: message('ai.card.testGeneration')}));
    expect(await screen.findByText(message('ai.toast.generationTestFailed'))).toBeInTheDocument();
    expect(test).toHaveBeenCalledWith({public_id: SPARK.public_id, chat_model: SPARK.chat_model, reasoning_effort: 'medium'});
    expect(within(card('DGX Spark 1')).getAllByText(/^✗ Test /)).toHaveLength(1);
  });

  it('tests the chat and the generation model apart in the editor with the form values', async () => {
    vi.spyOn(LlmIntegrationService, 'models').mockResolvedValue({ok: true, code: null, message: '', ms: 3, models: []});
    const test = vi
      .spyOn(LlmIntegrationService, 'test')
      .mockResolvedValueOnce({ok: true, steps: [{name: 'Sohbet modeli', ok: true, code: null, detail: 'Sohbet cevabı', ms: 1000}]})
      .mockResolvedValueOnce({ok: true, steps: [{name: 'Sohbet modeli', ok: true, code: null, detail: 'Üretim cevabı', ms: 2000}]});
    await openPage();
    fireEvent.click(within(card('DGX Spark 1')).getByRole('button', {name: message('ai.card.edit')}));
    const editor = await dialog(message('ai.editor.editTitle', {name: 'DGX Spark 1'}));
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.generationModel')), {target: {value: 'qwen/qwen3.8-27b'}});
    fireEvent.change(within(editor).getByLabelText(message('ai.editor.generationEffort')), {target: {value: 'high'}});
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.test')}));
    expect(await within(editor).findByText('Sohbet cevabı')).toBeInTheDocument();
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.testGeneration')}));
    expect(await within(editor).findByText('Üretim cevabı')).toBeInTheDocument();
    const connection = {
      public_id: SPARK.public_id,
      endpoint: SPARK.endpoint,
      temperature: 0,
      timeout_seconds: 900,
      seed: 42,
    };
    expect(test).toHaveBeenNthCalledWith(1, {...connection, chat_model: SPARK.chat_model, reasoning_effort: 'none'});
    expect(test).toHaveBeenNthCalledWith(2, {...connection, chat_model: 'qwen/qwen3.8-27b', reasoning_effort: 'high'});
    expect(within(editor).getByRole('heading', {level: 4, name: message('ai.editor.generationModel')})).toBeInTheDocument();
  });

  it('edits with the saved key masked, fetches the models at once, deletes the key and reports a cleared key', async () => {
    const models = vi
      .spyOn(LlmIntegrationService, 'models')
      .mockResolvedValue({ok: false, code: 'connect_refused', message: 'Model sunucusuna ulaşılamadı: bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı', ms: 3, models: []});
    const update = vi
      .spyOn(LlmIntegrationService, 'update')
      .mockImplementation(async (_item, body) => ({...BOTH, item: {...SPARK, has_key: false, ...body} as LlmIntegrationItem, key_cleared: true}));
    await openPage();
    fireEvent.click(within(card('DGX Spark 1')).getByRole('button', {name: message('ai.card.edit')}));
    const editor = await dialog(message('ai.editor.editTitle', {name: 'DGX Spark 1'}));
    expect(await within(editor).findByText(/bağlantı reddedildi/)).toHaveClass('msg', 'bad');
    expect(models).toHaveBeenCalledWith({public_id: SPARK.public_id, endpoint: SPARK.endpoint});
    expect(within(editor).getByLabelText(message('ai.editor.key'))).toHaveAttribute('placeholder', message('ai.editor.keySavedPlaceholder'));
    expect(within(editor).queryByText(message('ai.editor.keyHint'))).toBeNull();
    expect(within(editor).getByRole('checkbox', {name: message('ai.editor.keepActive')})).toBeChecked();

    fireEvent.click(within(editor).getByRole('checkbox', {name: message('ai.editor.clearKey')}));
    fireEvent.click(within(editor).getByRole('button', {name: message('ai.editor.save')}));
    expect(await screen.findByText(message('ai.toast.updated'))).toBeInTheDocument();
    expect(screen.getByText(message('ai.toast.keyCleared'))).toBeInTheDocument();
    expect(update).toHaveBeenCalledWith(SPARK, {
      name: 'DGX Spark 1',
      endpoint: SPARK.endpoint,
      chat_model: SPARK.chat_model,
      temperature: 0,
      timeout_seconds: 900,
      reasoning_effort: 'none',
      seed: 42,
      generation_model: '',
      generation_reasoning_effort: 'inherit',
      judge_reasoning_effort: 'inherit',
      api_key: '',
      activate: true,
      replace: false,
    });
  });

  it('closes the key field without key storage and tells nonprod to use https', async () => {
    await openPage(llmState([], {key_storage: false, environment: 'nonprod', accepts_http: false}));
    fireEvent.click(screen.getByRole('button', {name: message('ai.hero.new')}));
    const editor = await dialog(message('ai.editor.newTitle'));
    expect(within(editor).getByLabelText(message('ai.editor.key'))).toBeDisabled();
    expect(within(editor).getByText(message('ai.editor.keyUnavailable'))).toBeInTheDocument();
    expect(within(editor).getByText(message('ai.editor.endpointHintNonprod'))).toBeInTheDocument();
  });

  it('asks before taking the chat role from the active integration and does nothing when declined', async () => {
    const studio = {...STUDIO, chat_model: 'qwen3-8b'};
    const setActive = vi
      .spyOn(LlmIntegrationService, 'setActive')
      .mockImplementation(async (_item, _active, replace) => {
        if (!replace) throw new ApiError(409, 'x', 'llm_chat_role_taken');
        return llmState([{...SPARK, active: false}, {...studio, active: true}]);
      });
    const confirm = answerConfirm(false, true);
    await openPage(llmState([SPARK, studio]));
    const toggle = () => within(card('LM Studio')).getByRole('checkbox', {name: message('ai.card.activate')});
    fireEvent.click(toggle());
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(message('ai.confirm.replace', {name: 'DGX Spark 1'})));
    await waitFor(() => expect(toggle()).not.toBeChecked());
    expect(setActive).toHaveBeenCalledTimes(1);

    fireEvent.click(toggle());
    expect(await screen.findByText(message('ai.toast.activated'))).toBeInTheDocument();
    expect(screen.getByText(message('ai.toast.appliedLine', {name: 'LM Studio'}))).toBeInTheDocument();
    expect(setActive).toHaveBeenLastCalledWith(expect.objectContaining({public_id: STUDIO.public_id}), true, true);
    expect(within(card('LM Studio')).getByRole('checkbox', {name: message('ai.card.deactivate')})).toBeChecked();
  });

  it('asks before deleting and warns when the integration is the active one', async () => {
    const remove = vi.spyOn(LlmIntegrationService, 'remove').mockResolvedValue(llmState([STUDIO]));
    const confirm = answerConfirm(true);
    await openPage();
    fireEvent.click(within(card('DGX Spark 1')).getByRole('button', {name: message('ai.card.remove')}));
    expect(confirm).toHaveBeenCalledWith(message('ai.confirm.removeActive', {name: 'DGX Spark 1'}));
    expect(await screen.findByText(message('ai.toast.removed'))).toBeInTheDocument();
    expect(remove).toHaveBeenCalledWith(SPARK);
    expect(screen.queryByText('DGX Spark 1', {selector: '.integ b'})).toBeNull();
    expect(message('ai.confirm.remove', {name: 'LM Studio'})).toBe('“LM Studio” entegrasyonu silinsin mi?');
  });

  it('tests a saved integration from its card and records the result', async () => {
    const test = vi.spyOn(LlmIntegrationService, 'test').mockResolvedValue({
      ok: false,
      steps: [{name: 'Sunucu', ok: false, code: 'timeout', detail: 'Model sunucusuna ulaşılamadı: sunucu zamanında yanıt vermedi — adres erişilemez olabilir', ms: 10000}],
    });
    await openPage();
    const list = vi.mocked(LlmIntegrationService.list);
    const reads = list.mock.calls.length;
    fireEvent.click(within(card('LM Studio')).getByRole('button', {name: message('ai.card.testChat')}));
    expect(await screen.findByText(message('ai.toast.testFailed'))).toBeInTheDocument();
    expect(screen.getByText(/^✗ Sunucu: Model sunucusuna ulaşılamadı/)).toBeInTheDocument();
    expect(test).toHaveBeenCalledWith({public_id: STUDIO.public_id, record: true});
    await waitFor(() => expect(list.mock.calls.length).toBe(reads + 1));
  });

  it('lists a server\'s models under its card and makes one the chat model', async () => {
    vi.spyOn(LlmIntegrationService, 'models').mockResolvedValue({
      ok: true,
      code: null,
      message: '',
      ms: 5,
      models: [model('google/gemma-4-31b', {in_use: true, context: 131072}), model('qwen3-8b', {loaded: false})],
    });
    const update = vi
      .spyOn(LlmIntegrationService, 'update')
      .mockResolvedValue({...BOTH, item: SPARK, key_cleared: false});
    await openPage();
    const spark = card('DGX Spark 1');
    fireEvent.click(within(spark).getByRole('button', {name: message('ai.card.models')}));
    const table = await within(spark).findByRole('table');
    const rows = within(table).getAllByRole('row');
    expect(within(rows[1]).getByText(message('ai.models.inUse'))).toBeInTheDocument();
    expect(within(rows[1]).getByText('131.072')).toBeInTheDocument();
    expect(within(rows[1]).queryByRole('button')).toBeNull();
    expect(within(rows[2]).getByText(message('ai.models.notLoaded'))).toBeInTheDocument();
    fireEvent.click(within(rows[2]).getByRole('button', {name: message('ai.card.pick')}));
    expect(await screen.findByText(message('ai.toast.modelPicked'))).toBeInTheDocument();
    expect(screen.getByText(message('ai.toast.modelPickedLine', {name: 'DGX Spark 1', model: 'qwen3-8b'}))).toBeInTheDocument();
    expect(update).toHaveBeenCalledWith(SPARK, {chat_model: 'qwen3-8b', replace: false});
  });

  it('shows the model inventory, filters it Turkish-aware and warns about an unreachable server', async () => {
    vi.spyOn(LlmIntegrationService, 'inventory').mockResolvedValue({
      servers: [
        {
          public_id: SPARK.public_id,
          name: 'DGX Spark 1',
          active: true,
          ok: true,
          code: null,
          message: '',
          models: [model('google/gemma-4-31b', {in_use: true, context: 131072}), model('İnce-Model')],
        },
        {public_id: STUDIO.public_id, name: 'LM Studio', active: false, ok: true, code: null, message: '', models: [model('qwen3-8b')]},
        {
          public_id: '00000000-0000-4000-8000-00000000ffff',
          name: 'Kapalı',
          active: false,
          ok: false,
          code: 'connect_refused',
          message: 'Model sunucusuna ulaşılamadı: bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı',
          models: [],
        },
      ],
    });
    await openPage();
    fireEvent.click(screen.getByRole('button', {name: message('ai.inventory.open')}));
    const drawer = await dialog(message('ai.inventory.title'));
    const filter = await within(drawer).findByRole('searchbox', {name: message('ai.inventory.searchLabel')});
    expect(document.activeElement).toBe(filter);
    expect(within(drawer).getByText(/^Kapalı: Model sunucusuna ulaşılamadı/)).toHaveClass('msg', 'warn');
    expect(within(drawer).getAllByRole('row')).toHaveLength(4);
    expect(within(drawer).getByText(message('ai.inventory.chat'))).toHaveClass('tag', 'on');
    expect(within(drawer).getByText(message('ai.inventory.inactive'))).toBeInTheDocument();
    fireEvent.change(filter, {target: {value: 'ince'}});
    expect(within(drawer).getAllByRole('row').map((row) => row.querySelector('td')?.textContent)).toEqual([undefined, 'İnce-Model']);
  });

  it('opens the editor and the inventory from the command palette', async () => {
    vi.spyOn(LlmIntegrationService, 'inventory').mockResolvedValue({servers: []});
    serve(BOTH);
    renderApp('/admin/genel');
    await screen.findByRole('heading', {level: 1, name: message('admin.page.genel.label')});
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    const box = await screen.findByRole('textbox', {name: message('admin.palette.label')});
    fireEvent.change(box, {target: {value: 'yeni model'}});
    fireEvent.keyDown(box, {key: 'Enter'});
    expect(await dialog(message('ai.editor.newTitle'))).toBeInTheDocument();
    expect(screen.getByTestId('where').textContent).toBe('/admin/yapay-zeka');
    fireEvent.click(screen.getByRole('button', {name: message('ai.editor.cancel')}));

    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    const again = await screen.findByRole('textbox', {name: message('admin.palette.label')});
    fireEvent.change(again, {target: {value: 'envanter'}});
    fireEvent.keyDown(again, {key: 'Enter'});
    expect(await dialog(message('ai.inventory.title'))).toBeInTheDocument();
  });

  it('is not shown to kullanici', async () => {
    const list = serve(BOTH);
    clearAuth();
    signedIn('user');
    renderApp('/admin/yapay-zeka');
    expect(await screen.findByRole('heading', {name: message('access.forbidden.title')})).toBeInTheDocument();
    expect(list).not.toHaveBeenCalled();
  });
});
