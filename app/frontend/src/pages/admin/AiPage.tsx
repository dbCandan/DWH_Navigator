import {useEffect, useState} from 'react';
import {useLocation, useNavigate} from 'react-router';
import {Icon} from '@/components/admin/Icon';
import {PageHero} from '@/components/admin/PageHero';
import type {AiDrawerRequest} from '@/components/admin/nav';
import {Skeleton} from '@/components/admin/Skeleton';
import {IntegrationCard, type ModelsOutcome} from '@/components/ai/IntegrationCard';
import {IntegrationEditor, type WithConflict} from '@/components/ai/IntegrationEditor';
import {ModelInventory} from '@/components/ai/ModelInventory';
import {generationRole} from '@/components/ai/roles';
import {useIntl} from '@/contexts/IntlContext';
import {useLlmState} from '@/hooks/useLlmState';
import {useToast} from '@/hooks/useToast';
import {isRoleTaken, llmErrorText, stepLines} from '@/lib/llmText';
import {formatWhen} from '@/lib/format';
import {modelStatus} from '@/lib/modelStatus';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import type {LlmIntegrationCreated, LlmIntegrationItem, LlmIntegrationsState, LlmIntegrationUpdated} from '@/types/llm';
import '@/components/ai/ai.css';
import {confirmAction} from '@/lib/confirm';

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
      if (!(await confirmAction(t('ai.confirm.replace', {name: holder}), {action: t('ai.confirm.replaceAction')}))) return null;
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

  /** The generation model with the saved connection; not recorded, the saved test is the chat model's. */
  async function testGeneration(item: LlmIntegrationItem) {
    try {
      const answer = await LlmIntegrationService.test({public_id: item.public_id, ...generationRole(item)});
      toast(
        t(answer.ok ? 'ai.toast.generationTestOk' : 'ai.toast.generationTestFailed'),
        stepLines(answer.steps, t),
        !answer.ok,
      );
      return answer;
    } catch (error) {
      reportUnreachable(error);
      toast(t('ai.toast.testError'), [llmErrorText(error, t)], true);
      return null;
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
    if (!(await confirmAction(t(item.active ? 'ai.confirm.removeActive' : 'ai.confirm.remove', {name: item.name}), {action: t('ai.card.remove'), danger: true})))
      return;
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
        <PageHero icon="spark" title={label} />
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
  const held = holder ? (llm.items.find((item) => item.public_id === holder.public_id) ?? null) : null;
  const tested = held?.last_test ?? null;
  const tone = status.state === 'ok' ? 'ok' : status.state === 'down' ? 'bad' : 'warn';
  const activeCount = llm.items.filter((item) => item.active).length;
  // The active integration first; the rest keep the server's order.
  const rows = [...llm.items].sort((a, b) => Number(b.active) - Number(a.active));
  const add = () => show({kind: 'editor', item: null});
  return (
    <section className="page on" id="p-yapay-zeka" aria-label={label}>
      <PageHero
        icon="spark"
        title={label}
        description={t('admin.page.yapay-zeka.description')}
        actions={
          <>
            <button className="btn" type="button" onClick={() => show({kind: 'inventory'})}>
              <Icon name="list" />
              {t('ai.inventory.open')}
            </button>
            <button className="btn primary" type="button" onClick={add}>
              <Icon name="plus" />
              {t('ai.hero.new')}
            </button>
          </>
        }
        stats={[
          {
            label: t('ai.stat.model'),
            value: t(`ai.stat.state.${status.state}`),
            note: holder ? holder.model : undefined,
            tone,
          },
          {
            label: t('ai.stat.generation'),
            value: held ? generationRole(held).chat_model || t('ai.card.noModelShort') : t('ai.stat.state.none'),
            note: held && !held.generation_model.trim() ? t('ai.card.generationSame') : undefined,
          },
          {
            label: t('ai.stat.integrations'),
            value: llm.items.length,
            note: t('ai.stat.activeCount', {count: activeCount}),
          },
          {
            label: t('ai.stat.lastTest'),
            value: tested ? formatWhen(tested.at, t) : t('ai.card.untested'),
            note: tested ? t(tested.ok ? 'ai.stat.testOk' : 'ai.stat.testFailed') : undefined,
            tone: tested ? (tested.ok ? 'ok' : 'bad') : undefined,
          },
        ]}
      />
      <div className="fill scroll ai-body">
        {status.state === 'down' && holder ? (
          <div className="msg bad">{t('ai.hero.down', {name: holder.name, reason: status.detail})}</div>
        ) : status.state === 'none' && llm.items.length ? (
          <div className="msg warn">{t('ai.hero.none')}</div>
        ) : null}
        {llm.items.length ? (
          <section className="panel ai-list" aria-labelledby="ai-list-title">
            <h2 id="ai-list-title">{t('ai.list.title', {count: llm.items.length})}</h2>
            <div className="integs" key={version}>
              {rows.map((item) => (
                <IntegrationCard
                  key={item.public_id}
                  item={item}
                  onTest={() => testSaved(item)}
                  onTestGeneration={() => testGeneration(item)}
                  onModels={() => models(item)}
                  onPick={(model) => void pick(item, model)}
                  onEdit={() => show({kind: 'editor', item})}
                  onRemove={() => void remove(item)}
                  onActivate={(active) => activate(item, active)}
                />
              ))}
            </div>
          </section>
        ) : (
          <div className="panel ai-empty">
            <h2 id="ai-list-title">{t('ai.list.title', {count: 0})}</h2>
            <Icon name="server" />
            <p>{t('ai.list.empty')}</p>
            <button className="btn primary" type="button" onClick={add}>
              <Icon name="plus" />
              {t('ai.list.add')}
            </button>
          </div>
        )}
      </div>
      {drawer}
    </section>
  );
}
