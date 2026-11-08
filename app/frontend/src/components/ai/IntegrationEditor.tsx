import {useEffect, useRef, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Field} from '@/components/admin/Field';
import {Icon} from '@/components/admin/Icon';
import {SuggestCombobox} from '@/components/admin/SuggestCombobox';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {formatNumber} from '@/lib/format';
import {llmErrorText} from '@/lib/llmText';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import type {
  LlmIntegrationCreated,
  LlmIntegrationItem,
  LlmIntegrationsState,
  LlmIntegrationUpdated,
  LlmModelRow,
  LlmTestStep,
} from '@/types/llm';
import {TestSteps} from './TestSteps';
import './ai.css';

/** "Kaydet"/"Ekle" with another integration active asks before taking its role (Requirement 4). */
export type WithConflict = <T>(run: (replace: boolean) => Promise<T>) => Promise<T | null>;

interface Props {
  /** The integration to edit; null adds a new one. */
  item: LlmIntegrationItem | null;
  llm: LlmIntegrationsState | null;
  withConflict: WithConflict;
  onSaved: (answer: LlmIntegrationCreated | LlmIntegrationUpdated, name: string, active: boolean) => void;
  onClose: () => void;
}

const EFFORTS = [
  ['none', 'ai.editor.effort.none'],
  ['low', 'ai.editor.effort.low'],
  ['medium', 'ai.editor.effort.medium'],
  ['high', 'ai.editor.effort.high'],
  ['', 'ai.editor.effort.omit'],
] as const;

/** The generation role's reasoning: 'inherit' uses the chat model's own setting. */
const GENERATION_EFFORTS = [['inherit', 'ai.editor.effort.inherit'], ...EFFORTS] as const;

type Fetch =
  | {state: 'idle'}
  | {state: 'busy'}
  | {state: 'ok'; count: number}
  | {state: 'bad'; message: string};

type Test =
  | {state: 'idle'}
  | {state: 'busy'}
  | {state: 'done'; steps: LlmTestStep[]}
  | {state: 'bad'; message: string};

/**
 * The integration editor (llm-connection Requirement 19; admin.html AI.editor): 1 Bağlantı (name,
 * address, the masked key and "Kayıtlı anahtarı sil", "Bağlan ve modelleri getir"), 2 Model (the
 * chat model with the server's models as suggestions, "Gelişmiş"), 3 Test (the form's values,
 * nothing saved). Editing fetches the models at once; a server offering one model fills it in.
 */
export function IntegrationEditor({item, llm, withConflict, onSaved, onClose}: Props) {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const [name, setName] = useState(item?.name ?? '');
  const [endpoint, setEndpoint] = useState(item?.endpoint ?? '');
  const [apiKey, setApiKey] = useState('');
  const [clearKey, setClearKey] = useState(false);
  const [chatModel, setChatModel] = useState(item?.chat_model ?? '');
  const [temperature, setTemperature] = useState(String(item?.temperature ?? 0));
  const [timeout, setTimeoutSeconds] = useState(String(item?.timeout_seconds ?? 900));
  const [effort, setEffort] = useState(item?.reasoning_effort ?? 'none');
  const [seed, setSeed] = useState(String(item?.seed ?? 42));
  const [generationModel, setGenerationModel] = useState(item?.generation_model ?? '');
  const [generationEffort, setGenerationEffort] = useState(item?.generation_reasoning_effort ?? 'inherit');
  const [judgeEffort, setJudgeEffort] = useState(item?.judge_reasoning_effort ?? 'inherit');
  const [activate, setActivate] = useState(item ? item.active : true);
  const [offered, setOffered] = useState<LlmModelRow[]>([]);
  const [fetched, setFetched] = useState<Fetch>({state: 'idle'});
  const [tested, setTested] = useState<Test>({state: 'idle'});
  const [saving, setSaving] = useState(false);
  const fetchedOnOpen = useRef(false);

  const keyStorage = llm?.key_storage ?? true;
  const hasKey = item?.has_key ?? false;
  const typedKey = keyStorage && apiKey ? {api_key: apiKey} : {};
  const connection = () => ({
    endpoint: endpoint.trim(),
    chat_model: chatModel.trim(),
    temperature: Number(temperature),
    timeout_seconds: Number(timeout),
    reasoning_effort: effort,
    seed: Number(seed),
  });

  async function fetchModels() {
    setFetched({state: 'busy'});
    try {
      const answer = await LlmIntegrationService.models({
        ...(item ? {public_id: item.public_id} : {}),
        endpoint: endpoint.trim(),
        ...typedKey,
      });
      if (!answer.ok) {
        setFetched({state: 'bad', message: answer.message});
        return;
      }
      setOffered(answer.models);
      setFetched({state: 'ok', count: answer.models.length});
      if (answer.models.length === 1) setChatModel((current) => current || answer.models[0].id);
    } catch (error) {
      reportUnreachable(error);
      setFetched({state: 'bad', message: llmErrorText(error, t)});
    }
  }

  // Editing an integration fetches its server's models at once (the source clicked the button).
  useEffect(() => {
    if (!item || fetchedOnOpen.current) return;
    fetchedOnOpen.current = true;
    void fetchModels();
    // Once, when the editor opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function test() {
    setTested({state: 'busy'});
    try {
      const answer = await LlmIntegrationService.test({
        ...(item ? {public_id: item.public_id} : {}),
        ...connection(),
        ...typedKey,
      });
      setTested({state: 'done', steps: answer.steps});
    } catch (error) {
      reportUnreachable(error);
      setTested({state: 'bad', message: llmErrorText(error, t)});
    }
  }

  async function save() {
    const values = {
      name: name.trim(),
      ...connection(),
      generation_model: generationModel.trim(),
      generation_reasoning_effort: generationEffort,
      judge_reasoning_effort: judgeEffort,
    };
    if (!values.name || !values.endpoint) {
      toast(t('ai.toast.missing'), [t('ai.toast.missingLine')], true);
      return;
    }
    setSaving(true);
    try {
      const answer = item
        ? await withConflict((replace) =>
            LlmIntegrationService.update(item, {
              ...values,
              ...(clearKey ? {api_key: ''} : typedKey),
              activate,
              replace,
            }),
          )
        : await withConflict((replace) =>
            LlmIntegrationService.create({...values, ...typedKey, activate, replace}),
          );
      if (answer) {
        onSaved(answer, values.name, activate);
        return;
      }
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.saveFailed'), [llmErrorText(error, t)], true);
    }
    setSaving(false);
  }

  const nonprod = llm?.environment === 'nonprod';
  const keyHint = !keyStorage ? t('ai.editor.keyUnavailable') : hasKey ? undefined : t('ai.editor.keyHint');
  return (
    <Drawer
      title={item ? t('ai.editor.editTitle', {name: item.name}) : t('ai.editor.newTitle')}
      sub={t('ai.editor.sub')}
      onClose={onClose}
      foot={
        <>
          <label className="check grow">
            <input type="checkbox" checked={activate} onChange={(event) => setActivate(event.target.checked)} />
            {item?.active ? t('ai.editor.keepActive') : t('ai.editor.activateOnSave')}
          </label>
          <button className="btn ghost" type="button" onClick={onClose}>
            {t('ai.editor.cancel')}
          </button>
          <button className="btn primary" type="button" disabled={saving} onClick={() => void save()}>
            {item ? t('ai.editor.save') : t('ai.editor.add')}
          </button>
        </>
      }
    >
      <div className="form">
        <div className="stepno">
          <i>1</i>
          {t('ai.editor.stepConnection')}
        </div>
        <Field id="ai-name" label={t('ai.editor.name')} hint={t('ai.editor.nameHint')}>
          <input
            id="ai-name"
            type="text"
            placeholder={t('ai.editor.namePlaceholder')}
            autoComplete="off"
            aria-describedby="ai-name-hint"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="ai-endpoint" label={t('ai.editor.endpoint')} hint={t(nonprod ? 'ai.editor.endpointHintNonprod' : 'ai.editor.endpointHint')}>
          <input
            id="ai-endpoint"
            type="text"
            className="mono"
            placeholder={t('ai.editor.endpointPlaceholder')}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="ai-endpoint-hint"
            value={endpoint}
            onChange={(event) => setEndpoint(event.target.value)}
          />
        </Field>
        <Field id="ai-key" label={t('ai.editor.key')} hint={keyHint}>
          <input
            id="ai-key"
            type="password"
            className="mono"
            autoComplete="new-password"
            placeholder={hasKey ? t('ai.editor.keySavedPlaceholder') : t('ai.editor.keyPlaceholder')}
            aria-describedby={keyHint ? 'ai-key-hint' : undefined}
            disabled={!keyStorage}
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </Field>
        {hasKey && (
          <label className="check">
            <input type="checkbox" checked={clearKey} onChange={(event) => setClearKey(event.target.checked)} />
            {t('ai.editor.clearKey')}
          </label>
        )}
        <div>
          <button className="btn sm" type="button" disabled={fetched.state === 'busy'} onClick={() => void fetchModels()}>
            <Icon name="refresh" />
            {t('ai.editor.fetch')}
          </button>
        </div>
        <div className="note" aria-live="polite">
          {fetched.state === 'idle' && (item?.endpoint ? '' : t('ai.editor.fetchFirst'))}
          {fetched.state === 'busy' && t('ai.editor.connecting')}
          {fetched.state === 'ok' && <div className="msg ok">{t('ai.editor.fetched', {count: fetched.count})}</div>}
          {fetched.state === 'bad' && <div className="msg bad">{fetched.message}</div>}
        </div>
        <div className="stepno">
          <i>2</i>
          {t('ai.editor.stepModel')}
        </div>
        <Field id="ai-chat-model" label={t('ai.editor.chatModel')} hint={t('ai.editor.chatModelHint')}>
          <SuggestCombobox
            id="ai-chat-model"
            mono
            value={chatModel}
            options={offered.map((row) => ({
              value: row.id,
              note: row.context ? t('ai.editor.context', {context: formatNumber(row.context)}) : '',
            }))}
            listLabel={t('ai.editor.chatModelList')}
            placeholder={t('ai.editor.chatModelPlaceholder')}
            describedBy="ai-chat-model-hint"
            onChange={setChatModel}
          />
        </Field>
        <Field id="ai-generation-model" label={t('ai.editor.generationModel')} hint={t('ai.editor.generationModelHint')}>
          <SuggestCombobox
            id="ai-generation-model"
            mono
            value={generationModel}
            options={offered.map((row) => ({
              value: row.id,
              note: row.context ? t('ai.editor.context', {context: formatNumber(row.context)}) : '',
            }))}
            listLabel={t('ai.editor.chatModelList')}
            placeholder={t('ai.editor.generationModelPlaceholder')}
            describedBy="ai-generation-model-hint"
            onChange={setGenerationModel}
          />
        </Field>
        <div className="f2">
          <Field id="ai-generation-effort" label={t('ai.editor.generationEffort')} hint={t('ai.editor.generationEffortHint')}>
            <select
              id="ai-generation-effort"
              aria-describedby="ai-generation-effort-hint"
              value={generationEffort}
              onChange={(event) => setGenerationEffort(event.target.value)}
            >
              {GENERATION_EFFORTS.map(([value, key]) => (
                <option key={value} value={value}>
                  {t(key)}
                </option>
              ))}
            </select>
          </Field>
          <Field id="ai-judge-effort" label={t('ai.editor.judgeEffort')} hint={t('ai.editor.judgeEffortHint')}>
            <select
              id="ai-judge-effort"
              aria-describedby="ai-judge-effort-hint"
              value={judgeEffort}
              onChange={(event) => setJudgeEffort(event.target.value)}
            >
              {GENERATION_EFFORTS.map(([value, key]) => (
                <option key={value} value={value}>
                  {t(key)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <details className="fold">
          <summary>{t('ai.editor.advanced')}</summary>
          <div className="f2">
            <Field id="ai-temperature" label={t('ai.editor.temperature')} hint={t('ai.editor.temperatureHint')}>
              <input
                id="ai-temperature"
                type="number"
                min={0}
                max={2}
                step={0.1}
                aria-describedby="ai-temperature-hint"
                value={temperature}
                onChange={(event) => setTemperature(event.target.value)}
              />
            </Field>
            <Field id="ai-timeout" label={t('ai.editor.timeout')} hint={t('ai.editor.timeoutHint')}>
              <input
                id="ai-timeout"
                type="number"
                min={5}
                max={3600}
                step={5}
                aria-describedby="ai-timeout-hint"
                value={timeout}
                onChange={(event) => setTimeoutSeconds(event.target.value)}
              />
            </Field>
            <Field id="ai-effort" label={t('ai.editor.effort')} hint={t('ai.editor.effortHint')}>
              <select id="ai-effort" aria-describedby="ai-effort-hint" value={effort} onChange={(event) => setEffort(event.target.value)}>
                {EFFORTS.map(([value, key]) => (
                  <option key={value} value={value}>
                    {t(key)}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="ai-seed" label={t('ai.editor.seed')} hint={t('ai.editor.seedHint')}>
              <input
                id="ai-seed"
                type="number"
                min={-1}
                step={1}
                aria-describedby="ai-seed-hint"
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
              />
            </Field>
          </div>
        </details>
        <div className="stepno">
          <i>3</i>
          {t('ai.editor.stepTest')}
        </div>
        <div>
          <button className="btn sm" type="button" disabled={tested.state === 'busy'} onClick={() => void test()}>
            {tested.state === 'busy' ? (
              t('ai.testing')
            ) : (
              <>
                <Icon name="bolt" />
                {t('ai.editor.test')}
              </>
            )}
          </button>
          <span className="note ai-aside">{t('ai.editor.testNote')}</span>
        </div>
        <div aria-live="polite">
          {tested.state === 'busy' && <p className="note">{t('ai.editor.testing')}</p>}
          {tested.state === 'done' && <TestSteps steps={tested.steps} />}
          {tested.state === 'bad' && <div className="msg bad">{tested.message}</div>}
        </div>
      </div>
    </Drawer>
  );
}
