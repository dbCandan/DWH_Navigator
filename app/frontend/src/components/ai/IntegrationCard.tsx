import {useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {formatWhen} from '@/lib/format';
import type {LlmIntegrationItem, LlmModelRow} from '@/types/llm';
import {ModelTable} from './ModelTable';

/** A server's model list as the card shows it: the rows, or the failure's text. */
export type ModelsOutcome = {ok: true; rows: LlmModelRow[]} | {ok: false; message: string};

interface Props {
  item: LlmIntegrationItem;
  /** "Test et" with the saved values; the result is recorded (Requirement 15). */
  onTest: () => Promise<void>;
  onModels: () => Promise<ModelsOutcome>;
  /** "Sohbet modeli yap" in the model list. */
  onPick: (model: string) => void;
  onEdit: () => void;
  onRemove: () => void;
  /** The active/inactive switch; settles when the change is done, refused or failed. */
  onActivate: (active: boolean) => Promise<void>;
}

/**
 * An integration's card (llm-connection Requirement 19; admin.html AI.card): name, address and
 * the active switch; Aktif/Pasif, Anahtar kayıtlı/Anahtarsız and the last test; the chat model or
 * "Model seçilmedi …"; "Test et", "Modeller" (opens the server's models below), "Düzenle", "Sil".
 */
export function IntegrationCard({item, onTest, onModels, onPick, onEdit, onRemove, onActivate}: Props) {
  const {t} = useIntl();
  const [testing, setTesting] = useState(false);
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

  return (
    <section className={'card integ' + (item.active ? '' : ' off')}>
      <div className="ih">
        <div className="nm">
          <b>{item.name}</b>
          <div className="url">{item.endpoint}</div>
        </div>
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
      <div className="tags">
        <span className={'tag' + (item.active ? ' on' : '')}>{t(item.active ? 'ai.card.active' : 'ai.card.inactive')}</span>
        <span className="tag">{t(item.has_key ? 'ai.card.keySaved' : 'ai.card.noKey')}</span>
        {lastTest ? (
          <span className={'tag ' + (lastTest.ok ? 'on' : 'bad')} title={lastTest.summary}>
            {t(lastTest.ok ? 'ai.card.testedOk' : 'ai.card.testedFailed', {when: formatWhen(lastTest.at, t)})}
          </span>
        ) : (
          <span className="tag">{t('ai.card.untested')}</span>
        )}
      </div>
      {item.chat_model ? (
        <>
          <div className="model">
            <span className="note">{t('ai.card.chatModel')}</span>
            <b>{item.chat_model}</b>
          </div>
          <div className="model">
            <span className="note">{t('ai.card.generationModel')}</span>
            {item.generation_model ? <b>{item.generation_model}</b> : <span className="note">{t('ai.card.generationSame')}</span>}
          </div>
        </>
      ) : (
        <div className="msg warn">{t('ai.card.noModel')}</div>
      )}
      <div className="acts">
        <button className="btn sm" type="button" disabled={testing} onClick={() => void test()}>
          {testing ? t('ai.testing') : t('ai.test')}
        </button>
        <button className="btn sm" type="button" disabled={models === 'loading'} onClick={() => void toggleModels()}>
          {t('ai.card.models')}
        </button>
        <button className="btn sm" type="button" onClick={onEdit}>
          {t('ai.card.edit')}
        </button>
        <button className="btn sm ghost danger" type="button" onClick={onRemove}>
          {t('ai.card.remove')}
        </button>
      </div>
      <div>
        {models !== null && models !== 'loading' && models.ok && (
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
        )}
        {models !== null && models !== 'loading' && !models.ok && <div className="msg bad">{models.message}</div>}
      </div>
    </section>
  );
}
