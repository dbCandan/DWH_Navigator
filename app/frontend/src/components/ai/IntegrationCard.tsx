import {useState, type ReactNode} from 'react';
import {Icon} from '@/components/admin/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {formatWhen} from '@/lib/format';
import type {LlmIntegrationItem, LlmModelRow, LlmTestResult} from '@/types/llm';
import {ModelTable} from './ModelTable';
import {effortKey, generationRole} from './roles';

/** A server's model list as the row shows it: the rows, or the failure's text. */
export type ModelsOutcome = {ok: true; rows: LlmModelRow[]} | {ok: false; message: string};

/** A test as a role shows it: when, whether it passed, and its steps for the tooltip. */
type Tested = {at: string; ok: boolean; summary: string};

interface Props {
  item: LlmIntegrationItem;
  /** "Test et" with the saved values; the result is recorded (Requirement 15). */
  onTest: () => Promise<void>;
  /** "Test et" on the generation model with the saved values; nothing is recorded (null: no answer). */
  onTestGeneration: () => Promise<LlmTestResult | null>;
  onModels: () => Promise<ModelsOutcome>;
  /** "Sohbet modeli yap" in the model list. */
  onPick: (model: string) => void;
  onEdit: () => void;
  onRemove: () => void;
  /** The active/inactive switch; settles when the change is done, refused or failed. */
  onActivate: (active: boolean) => Promise<void>;
}

/** One role of an integration: its model, its reasoning and last test, and its own "Test et" at the right. */
function Role({
  label,
  model,
  empty,
  detail,
  tested,
  untestedTitle,
  testLabel,
  testing,
  disabled,
  onTest,
}: {
  label: string;
  model: string;
  empty: ReactNode;
  detail: string;
  tested: Tested | null;
  untestedTitle?: string;
  testLabel: string;
  testing: boolean;
  disabled: boolean;
  onTest: () => void;
}) {
  const {t} = useIntl();
  return (
    <div className="ai-cell ai-role-cell" role="group" aria-label={label}>
      <span className="ai-cell-k">{label}</span>
      <div className="ai-cell-main">{model ? <b className="ai-model">{model}</b> : empty}</div>
      <div className="ai-cell-sub" title={detail}>
        {detail}
      </div>
      <div className="ai-cell-sub">
        {tested ? (
          <span className={'ai-tst ' + (tested.ok ? 'ok' : 'bad')} title={tested.summary}>
            {t(tested.ok ? 'ai.card.testedOk' : 'ai.card.testedFailed', {when: formatWhen(tested.at, t)})}
          </span>
        ) : (
          <span className="ai-tst" title={untestedTitle}>
            {t('ai.card.untested')}
          </span>
        )}
      </div>
      <button className="btn sm ai-cell-test" type="button" aria-label={testLabel} disabled={testing || disabled} onClick={onTest}>
        <Icon name="bolt" />
        {testing ? t('ai.testing') : t('ai.test')}
      </button>
    </div>
  );
}

/**
 * An integration as one row of the list (llm-connection Requirement 19), in the columns the list's
 * head names: a light for its health, name, address and key; the chat model and the generation
 * model (the dictionary update's), each with its reasoning, last test and own "Test et"; then
 * "Modeller" (the server's models open below), "Düzenle", "Sil" and the active switch. Each cell
 * is three short lines, so the columns line up; the cells carry their own label for narrow screens.
 */
export function IntegrationCard({item, onTest, onTestGeneration, onModels, onPick, onEdit, onRemove, onActivate}: Props) {
  const {t} = useIntl();
  const [testing, setTesting] = useState(false);
  const [generationTesting, setGenerationTesting] = useState(false);
  const [generationTest, setGenerationTest] = useState<Tested | null>(null);
  const [models, setModels] = useState<ModelsOutcome | 'loading' | null>(null);
  const [switching, setSwitching] = useState<boolean | null>(null);
  const switchLabel = t(item.active ? 'ai.card.deactivate' : 'ai.card.activate');
  const lastTest = item.last_test;

  async function test() {
    setTesting(true);
    try {
      await onTest();
    } finally {
      setTesting(false);
    }
  }

  async function testGeneration() {
    setGenerationTesting(true);
    try {
      const answer = await onTestGeneration();
      if (answer) {
        const summary = answer.steps.map((step) => `${step.name}: ${step.ok ? '✓' : '✗'}`).join('; ');
        setGenerationTest({at: new Date().toISOString(), ok: answer.ok, summary: `${summary} — ${t('ai.card.generationTestNote')}`});
      }
    } finally {
      setGenerationTesting(false);
    }
  }

  async function toggleModels() {
    if (models !== null) {
      setModels(null);
      return;
    }
    setModels('loading');
    setModels(await onModels());
  }

  async function activate(active: boolean) {
    setSwitching(active);
    try {
      await onActivate(active);
    } finally {
      setSwitching(null);
    }
  }

  const effort = (value: string) => {
    const key = effortKey(value);
    return key ? t(key) : value;
  };
  const generation = generationRole(item);
  const health = !item.active ? 'off' : lastTest ? (lastTest.ok ? 'ok' : 'bad') : 'idle';
  const led = health === 'idle' ? 'warn' : health;
  return (
    <section className={'ai-integ ' + health} aria-label={item.name}>
      <div className="ai-integ-row">
        <div className="ai-cell ai-name-cell">
          <div className="ai-cell-main">
            <span className={'led ' + led} aria-hidden="true" />
            <b className="ai-name">{item.name}</b>
            <span className={'tag' + (item.active ? ' on' : '')}>{t(item.active ? 'ai.card.active' : 'ai.card.inactive')}</span>
          </div>
          <div className="ai-cell-sub ai-url" title={item.endpoint}>
            {item.endpoint}
          </div>
          <div className="ai-cell-sub">{t(item.has_key ? 'ai.card.keySaved' : 'ai.card.noKey')}</div>
        </div>
        <Role
          label={t('ai.card.chatModel')}
          model={item.chat_model}
          empty={<span className="ai-none">{t('ai.card.noModelShort')}</span>}
          detail={t('ai.card.effort', {effort: effort(item.reasoning_effort)})}
          tested={lastTest}
          testLabel={t('ai.card.testChat')}
          testing={testing}
          disabled={false}
          onTest={() => void test()}
        />
        <Role
          label={t('ai.card.generationModel')}
          model={item.generation_model}
          empty={<span className="ai-same">{t('ai.card.generationSame')}</span>}
          detail={t('ai.card.generationEfforts', {
            effort: effort(item.generation_reasoning_effort),
            judge: effort(item.judge_reasoning_effort),
          })}
          tested={generationTest}
          untestedTitle={t('ai.card.generationTestNote')}
          testLabel={t('ai.card.testGeneration')}
          testing={generationTesting}
          disabled={!generation.chat_model}
          onTest={() => void testGeneration()}
        />
        <div className="ai-integ-acts">
          <button className="btn sm" type="button" aria-expanded={models !== null && models !== 'loading'} disabled={models === 'loading'} onClick={() => void toggleModels()}>
            <Icon name="list" />
            {t('ai.card.models')}
          </button>
          <button className="btn sm" type="button" onClick={onEdit}>
            {t('ai.card.edit')}
          </button>
          <button className="btn sm ghost danger" type="button" onClick={onRemove}>
            {t('ai.card.remove')}
          </button>
          <label className="switch" title={switchLabel}>
            <input
              type="checkbox"
              aria-label={switchLabel}
              checked={switching ?? item.active}
              disabled={switching !== null}
              onChange={(event) => void activate(event.target.checked)}
            />
            <span />
          </label>
        </div>
      </div>
      {item.chat_model ? null : <div className="msg warn">{t('ai.card.noModel')}</div>}
      {models !== null && models !== 'loading' ? (
        <div className="ai-integ-models">
          {models.ok ? (
            <ModelTable
              rows={models.rows}
              action={(row) =>
                item.chat_model === row.id ? null : (
                  <button className="btn sm" type="button" onClick={() => onPick(row.id)}>
                    {t('ai.card.pick')}
                  </button>
                )
              }
            />
          ) : (
            <div className="msg bad">{models.message}</div>
          )}
        </div>
      ) : null}
    </section>
  );
}
