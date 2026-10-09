import {useEffect, useState} from 'react';
import {useLocation, useNavigate} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {PageHead} from '@/components/admin/PageHead';
import type {AiDrawerRequest} from '@/components/admin/nav';
import {Skeleton} from '@/components/admin/Skeleton';
import {IntegrationCard, type ModelsOutcome} from '@/components/ai/IntegrationCard';
import {IntegrationEditor, type WithConflict} from '@/components/ai/IntegrationEditor';
import {ModelInventory} from '@/components/ai/ModelInventory';
import {useIntl} from '@/contexts/IntlContext';
import {useLlmState} from '@/hooks/useLlmState';
import {useToast} from '@/hooks/useToast';
import {isRoleTaken, llmErrorText, stepLines} from '@/lib/llmText';
import {modelStatus} from '@/lib/modelStatus';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import type {LlmIntegrationCreated, LlmIntegrationItem, LlmIntegrationsState, LlmIntegrationUpdated} from '@/types/llm';
import '@/components/ai/ai.css';

type Open = {kind: 'editor'; item: LlmIntegrationItem | null} | {kind: 'inventory'} | null;

function requestOf(state: unknown): AiDrawerRequest | null {
  const open = (state as {open?: unknown} | null)?.open;
  return open === 'editor' || open === 'inventory' ? open : null;
}

/** The connection state inside a save answer, without the saved item. */
function stateOf(answer: LlmIntegrationCreated | LlmIntegrationUpdated): LlmIntegrationsState {
  const {items, total, active, model_state, environment, accepts_http, key_storage} = answer;
  return {items, total, active, model_state, environment, accepts_http, key_storage};
}

/**
 * The admin screen's "Yapay zekâ" page (data-dictionary/PRDs/003-llm-connection Requirement 19;
 * admin.html AI): the active chat model, the integration cards, the editor and the model
 * inventory drawers. Every change answers with the new state, which the shell's badge and system
 * status share. Conflicts and deletions are confirmed in the browser's dialog, as in the source.
 */
export default function AiPage() {
  const {t} = useIntl();
  const {toast, reportUnreachable} = useToast();
  const {llm, version, failure, reload, adopt} = useLlmState();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState<Open>(null);
  const [opened, setOpened] = useState(0);
  const [handled, setHandled] = useState<string | null>(null);
  const [heroTesting, setHeroTesting] = useState(false);
  const label = t('admin.page.yapay-zeka.label');

  // "Yeni model entegrasyonu" and "Model envanteri" in the command palette open their drawer here.
  const request = requestOf(location.state);
  if (request && handled !== location.key) {
    setHandled(location.key);
    setOpen(request === 'editor' ? {kind: 'editor', item: null} : {kind: 'inventory'});
    setOpened(opened + 1);
  }
  useEffect(() => {
    if (request) navigate(location.pathname, {replace: true, state: null});
  }, [request, location.pathname, navigate]);

  function show(next: Open) {
    setOpen(next);
    setOpened((count) => count + 1);
  }

  const withConflict: WithConflict = async (run) => {
    try {
      return await run(false);
    } catch (error) {
      if (!isRoleTaken(error)) throw error;
      let holder = llm?.active?.name;
      if (!holder) {
        const fresh = await LlmIntegrationService.list();
        adopt(fresh);
        holder = fresh.active?.name ?? '';
      }
      if (!window.confirm(t('ai.confirm.replace', {name: holder}))) return null;
      return run(true);
    }
  };

  async function testSaved(item: Pick<LlmIntegrationItem, 'public_id'>) {
    try {
      const answer = await LlmIntegrationService.test({public_id: item.public_id, record: true});
      toast(t(answer.ok ? 'ai.toast.testOk' : 'ai.toast.testFailed'), stepLines(answer.steps, t), !answer.ok);
      await reload();
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.testError'), [llmErrorText(error, t)], true);
    }
  }

  async function heroTest(item: Pick<LlmIntegrationItem, 'public_id'>) {
    setHeroTesting(true);
    try {
      await testSaved(item);
    } finally {
      setHeroTesting(false);
    }
  }

  async function models(item: LlmIntegrationItem): Promise<ModelsOutcome> {
    try {
      const answer = await LlmIntegrationService.models({public_id: item.public_id});
      return answer.ok ? {ok: true, rows: answer.models} : {ok: false, message: answer.message};
    } catch (error) {
      reportUnreachable(error);
      return {ok: false, message: llmErrorText(error, t)};
    }
  }

  async function pick(item: LlmIntegrationItem, model: string) {
    try {
      const answer = await withConflict((replace) => LlmIntegrationService.update(item, {chat_model: model, replace}));
      if (answer) {
        toast(t('ai.toast.modelPicked'), [t('ai.toast.modelPickedLine', {name: item.name, model})]);
        adopt(stateOf(answer));
      }
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.saveFailed'), [llmErrorText(error, t)], true);
    }
  }

  async function activate(item: LlmIntegrationItem, active: boolean) {
    try {
      const state = await withConflict((replace) => LlmIntegrationService.setActive(item, active, replace));
      if (state) {
        toast(t(active ? 'ai.toast.activated' : 'ai.toast.deactivated'), [t('ai.toast.appliedLine', {name: item.name})]);
        adopt(state);
      }
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.changeFailed'), [llmErrorText(error, t)], true);
    }
  }

  async function remove(item: LlmIntegrationItem) {
    if (!window.confirm(t(item.active ? 'ai.confirm.removeActive' : 'ai.confirm.remove', {name: item.name}))) return;
    try {
      const state = await LlmIntegrationService.remove(item);
      toast(t('ai.toast.removed'), [item.name]);
      adopt(state);
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.removeFailed'), [llmErrorText(error, t)], true);
    }
  }

  function saved(answer: LlmIntegrationCreated | LlmIntegrationUpdated, name: string, active: boolean, editing: boolean) {
    setOpen(null);
    toast(t(editing ? 'ai.toast.updated' : 'ai.toast.added'), [
      t(active ? 'ai.toast.savedActive' : 'ai.toast.savedInactive', {name}),
    ]);
    if ('key_cleared' in answer && answer.key_cleared) toast(t('ai.toast.keyCleared'));
    adopt(stateOf(answer));
  }

  const drawer =
    open?.kind === 'editor' ? (
      <IntegrationEditor
        key={opened}
        item={open.item}
        llm={llm}
        withConflict={withConflict}
        onSaved={(answer, name, active) => saved(answer, name, active, open.item !== null)}
        onClose={() => setOpen(null)}
      />
    ) : open?.kind === 'inventory' ? (
      <ModelInventory key={opened} onClose={() => setOpen(null)} />
    ) : null;

  if (llm === null)
    return (
      <section className="page on" id="p-yapay-zeka" aria-label={label}>
        <PageHead title={label} />
        {failure ? (
          <div className="msg bad">{t('admin.pageFailed', {reason: llmErrorText(failure, t)})}</div>
        ) : (
          <Skeleton />
        )}
        {drawer}
      </section>
    );

  const status = modelStatus(llm, t);
  const holder = status.active;
  return (
    <section className="page on" id="p-yapay-zeka" aria-label={label}>
      <PageHead
        title={label}
        description={t('admin.page.yapay-zeka.description')}
        actions={
          <button className="btn" type="button" onClick={() => show({kind: 'inventory'})}>
            <Icon name="list" />
            {t('ai.inventory.open')}
          </button>
        }
      />
      <section className="card">
        <div className="hero">
          <div className={'orb ' + (status.state === 'ok' ? 'ok' : status.state === 'down' ? 'bad' : 'none')}>
            <Icon name="spark" />
          </div>
          <div>
            <div className="note">{t('ai.hero.role')}</div>
            <h2>{holder ? holder.model : t('ai.status.none')}</h2>
            <div className="muted">
              {status.state === 'ok' && holder
                ? t('ai.hero.ok', {name: holder.name})
                : status.state === 'down' && holder
                  ? t('ai.hero.down', {name: holder.name, reason: status.detail})
                  : t('ai.hero.none')}
            </div>
          </div>
          <div className="acts">
            {holder ? (
              <button className="btn" type="button" disabled={heroTesting} onClick={() => void heroTest(holder)}>
                {heroTesting ? (
                  t('ai.testing')
                ) : (
                  <>
                    <Icon name="bolt" />
                    {t('ai.test')}
                  </>
                )}
              </button>
            ) : null}
            <button className="btn primary" type="button" onClick={() => show({kind: 'editor', item: null})}>
              <Icon name="plus" />
              {t('ai.hero.new')}
            </button>
          </div>
        </div>
      </section>
      <div className="card-h ai-list-head">
        <h2>{t('ai.list.title', {count: llm.items.length})}</h2>
      </div>
      {llm.items.length ? (
        <div className="fill scroll">
          <div className="integs" key={version}>
            {llm.items.map((item) => (
              <IntegrationCard
                key={item.public_id}
                item={item}
                onTest={() => testSaved(item)}
                onModels={() => models(item)}
                onPick={(model) => void pick(item, model)}
                onEdit={() => show({kind: 'editor', item})}
                onRemove={() => void remove(item)}
                onActivate={(active) => activate(item, active)}
              />
            ))}
          </div>
        </div>
      ) : (
        <section className="card">
          <p className="empty">{t('ai.list.empty')}</p>
          <div className="more">
            <button className="btn primary" type="button" onClick={() => show({kind: 'editor', item: null})}>
              <Icon name="plus" />
              {t('ai.list.add')}
            </button>
          </div>
        </section>
      )}
      {drawer}
    </section>
  );
}
