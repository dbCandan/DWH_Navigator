import {useCallback, useMemo, useRef, useState, type ReactNode} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {ToastContext} from '@/hooks/useToast';
import {isUnreachable} from '@/lib/apiClient';

interface Toast {
  id: number;
  title: string;
  lines: string[];
  bad: boolean;
}

const UNREACHABLE_EVERY_MS = 15000;

/** The admin screen's notices (admin.html .toasts). */
export function ToastProvider({children}: {children: ReactNode}) {
  const {t} = useIntl();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const unreachableAt = useRef(0);

  const show = useCallback((title: string, lines: (string | null | undefined | false)[], bad: boolean) => {
    const id = ++nextId.current;
    setToasts((current) => [...current, {id, title, lines: lines.filter((line): line is string => Boolean(line)), bad}]);
    return () => setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    (title: string, lines: (string | null | undefined | false)[] = [], bad = false) => {
      window.setTimeout(show(title, lines, bad), bad ? 11000 : 6500);
    },
    [show],
  );

  const hold = useCallback(
    (title: string, lines: (string | null | undefined | false)[] = []) => show(title, lines, false),
    [show],
  );

  const reportUnreachable = useCallback(
    (error: unknown) => {
      if (!isUnreachable(error)) return false;
      if (Date.now() - unreachableAt.current > UNREACHABLE_EVERY_MS) {
        unreachableAt.current = Date.now();
        toast(t('admin.unreachable.title'), [t('admin.unreachable.body')], true);
      }
      return true;
    },
    [t, toast],
  );

  const value = useMemo(() => ({toast, hold, reportUnreachable}), [toast, hold, reportUnreachable]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" id="toasts" role="status" aria-live="polite">
        {toasts.map((item) => (
          <div key={item.id} className={'toast' + (item.bad ? ' bad' : '')}>
            <b>{item.title}</b>
            {item.lines.map((line, index) => (
              <div key={index}>{line}</div>
            ))}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
