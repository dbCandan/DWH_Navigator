import {useCallback, useMemo, useRef, useState, type ReactNode} from 'react';
import {LlmStateContext} from '@/hooks/useLlmState';
import {useToast} from '@/hooks/useToast';
import {LlmIntegrationService} from '@/services/llmIntegrations';
import type {LlmIntegrationsState} from '@/types/llm';

interface Held {
  llm: LlmIntegrationsState | null;
  version: number;
  failure: unknown;
}

/**
 * Holds the model connections' state for the admin shell and the AI page. A read that an
 * action's newer answer overtook is dropped; an unreachable server is reported as a notice.
 */
export function LlmStateProvider({children}: {children: ReactNode}) {
  const {reportUnreachable} = useToast();
  const [held, setHeld] = useState<Held>({llm: null, version: 0, failure: null});
  const latest = useRef(0);

  const adopt = useCallback((llm: LlmIntegrationsState) => {
    latest.current += 1;
    setHeld((current) => ({llm, version: current.version + 1, failure: null}));
  }, []);

  const reload = useCallback(async () => {
    const mine = ++latest.current;
    try {
      const llm = await LlmIntegrationService.list();
      if (mine === latest.current) setHeld((current) => ({llm, version: current.version + 1, failure: null}));
    } catch (error) {
      reportUnreachable(error);
      if (mine === latest.current) setHeld((current) => ({...current, failure: current.llm ? null : error}));
    }
  }, [reportUnreachable]);

  const value = useMemo(() => ({...held, reload, adopt}), [held, reload, adopt]);
  return <LlmStateContext.Provider value={value}>{children}</LlmStateContext.Provider>;
}
