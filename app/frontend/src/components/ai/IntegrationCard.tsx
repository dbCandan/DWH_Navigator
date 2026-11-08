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

/** One role of an integration: its model, its reasoning, its last test and its own "Test et". */
function Role({
  kind,
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
  kind: 'chat' | 'generation';
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
    <div className={'role ' + kind} role="group" aria-label={label}>
      <span className="k">{label}</span>
      {model ? <b>{model}</b> : empty}
      <div className="role-meta">
        <span className="note">{detail}</span>
        {tested ? (
          <span className={'tst ' + (tested.ok ? 'ok' : 'bad')} title={tested.summary}>
            {t(tested.ok ? 'ai.card.testedOk' : 'ai.card.testedFailed', {when: formatWhen(tested.at, t)})}
          </span>
        ) : (
          <span className="tst" title={untestedTitle}>
            {t('ai.card.untested')}
          </span>
        )}
        <button className="btn sm" type="button" aria-label={testLabel} disabled={testing || disabled} onClick={onTest}>
          <Icon name="bolt" />
          {testing ? t('ai.testing') : t('ai.test')}
        </button>
      </div>
    </div>
  );
}

/**
 * An integration as one compact row (llm-connection Requirement 19): a light for its health,
 * name, address and key; the chat model and the generation model (the dictionary update's) side
 * by side, each with its reasoning, last test and own "Test et"; then "Modeller" (the server's
 * models open below), "Düzenle", "Sil" and the active switch.
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
  return (
    <section className={'integ ' + health} aria-label={item.name}>
      <div className="ir">
        <span className={'led ' + health} aria-hidden="true" />
        <div className="nm">
          <div className="nm-t">
            <b>{item.name}</b>
            <span className={'tag' + (item.active ? ' on' : '')}>{t(item.active ? 'ai.card.active' : 'ai.card.inactive')}</span>
          </div>
          <div className="url">{item.endpoint}</div>
          <div className="key">{t(item.has_key ? 'ai.card.keySaved' : 'ai.card.noKey')}</div>
        </div>
        <Role
          kind="chat"
          label={t('ai.card.chatModel')}
          model={item.chat_model}
          empty={<span className="none">{t('ai.card.noModelShort')}</span>}
          detail={t('ai.card.effort', {effort: effort(item.reasoning_effort)})}
          tested={lastTest}
          testLabel={t('ai.card.testChat')}
          testing={testing}
          disabled={false}
          onTest={() => void test()}
        />
        <Role
          kind="generation"
          label={t('ai.card.generationModel')}
          model={item.generation_model}
          empty={<span className="same">{t('ai.card.generationSame')}</span>}
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
        <div className="acts">
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
        <div className="models">
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
