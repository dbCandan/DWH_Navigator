import {useEffect, useMemo, useRef, useState} from 'react';
import {Drawer} from '@/components/admin/Drawer';
import {Skeleton} from '@/components/admin/Skeleton';
import {useIntl} from '@/contexts/IntlContext';
import {useToast} from '@/hooks/useToast';
import {fold} from '@/lib/fold';
import {formatNumber} from '@/lib/format';
import {llmErrorText} from '@/lib/llmText';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import type {LlmInventory} from '@/types/llm';
import './ai.css';

type Loaded = {state: 'loading'} | {state: 'ready'; inventory: LlmInventory} | {state: 'failed'; message: string};

/**
 * The model inventory (llm-connection Requirement 19; admin.html AI.inventory): every
 * integration's served models, filtered Turkish-aware by "Model ara…", with "pasif" and "Sohbet"
 * marks and a warning for each server that could not be reached.
 */
export function ModelInventory({onClose}: {onClose: () => void}) {
  const {t} = useIntl();
  const {reportUnreachable} = useToast();
  const [loaded, setLoaded] = useState<Loaded>({state: 'loading'});
  const [query, setQuery] = useState('');
  const filter = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let open = true;
    LlmIntegrationService.inventory()
      .then((inventory) => {
        if (open) setLoaded({state: 'ready', inventory});
      })
      .catch((error: unknown) => {
        reportUnreachable(error);
        if (open) setLoaded({state: 'failed', message: llmErrorText(error, t)});
      });
    return () => {
      open = false;
    };
  }, [reportUnreachable, t]);

  const ready = loaded.state === 'ready';
  useEffect(() => {
    if (ready) filter.current?.focus();
  }, [ready]);

  const rows = useMemo(
    () =>
      loaded.state === 'ready'
        ? loaded.inventory.servers.flatMap((server) => server.models.map((model) => ({model, server})))
        : [],
    [loaded],
  );
  const folded = fold(query);
  const shown = folded ? rows.filter(({model}) => fold(model.id).includes(folded)) : rows;

  return (
    <Drawer title={t('ai.inventory.title')} sub={t('ai.inventory.sub')} wide onClose={onClose}>
      {loaded.state === 'loading' && <Skeleton />}
      {loaded.state === 'failed' && <div className="msg bad">{loaded.message}</div>}
      {loaded.state === 'ready' && (
        <>
          {loaded.inventory.servers
            .filter((server) => !server.ok)
            .map((server) => (
              <div className="msg warn" key={server.public_id}>
                {t('ai.inventory.unreachable', {name: server.name, reason: server.message})}
              </div>
            ))}
          <input
            type="search"
            ref={filter}
            placeholder={t('ai.inventory.search')}
            aria-label={t('ai.inventory.searchLabel')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="ai-gap" />
          <div>
            <table className="t">
              <thead>
                <tr>
                  <th>{t('ai.models.model')}</th>
                  <th>{t('ai.inventory.integration')}</th>
                  <th>{t('ai.models.context')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shown.map(({model, server}) => (
                  <tr key={server.public_id + '\n' + model.id}>
                    <td className="nm">{model.id}</td>
                    <td>
                      {server.name}
                      {server.active ? null : <span className="tag ai-tag-gap">{t('ai.inventory.inactive')}</span>}
                    </td>
                    <td className="r">{model.context ? formatNumber(model.context) : t('ai.models.noContext')}</td>
                    <td>{model.in_use ? <span className="tag on">{t('ai.inventory.chat')}</span> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Drawer>
  );
}
