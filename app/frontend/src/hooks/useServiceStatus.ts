import {useCallback, useEffect, useRef, useState} from 'react';
import {AnalysisService} from '@/services/analyses';
import type {ServiceStatus} from '@/types/analysis';

/** How often the main screen asks again: the model server may come and go. */
export const STATUS_INTERVAL_MS = 60000;

export interface ServiceStatusState {
  /** The latest answer; null before the first one and after a failed request. */
  status: ServiceStatus | null;
  /** The last request failed ("Sunucuya ulaşılamadı"). */
  failed: boolean;
  /** Ask again now (after an answer the analyst did not write). */
  reload: () => void;
}

/**
 * `GET /status` on opening, every 60 seconds and on demand (dictionary-explorer Requirement 2,
 * question-analysis Requirement 22).
 */
export function useServiceStatus(): ServiceStatusState {
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const live = useRef(true);

  const reload = useCallback(() => {
    AnalysisService.status().then(
      (answer) => {
        if (!live.current) return;
        setStatus(answer);
        setFailed(false);
      },
      () => {
        if (!live.current) return;
        setStatus(null);
        setFailed(true);
      },
    );
  }, []);

  useEffect(() => {
    live.current = true;
    reload();
    const timer = window.setInterval(reload, STATUS_INTERVAL_MS);
    return () => {
      live.current = false;
      window.clearInterval(timer);
    };
  }, [reload]);

  return {status, failed, reload};
}
