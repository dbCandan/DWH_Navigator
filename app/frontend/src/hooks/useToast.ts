import {createContext, useContext} from 'react';

export interface ToastValue {
  /** Show a notice: success stays about 6.5 s, an error 11 s (search-settings Requirement 24). */
  toast: (title: string, lines?: (string | null | undefined | false)[], bad?: boolean) => void;
  /** Show a notice until the returned function removes it ("İçe aktarılıyor…" while a file loads). */
  hold: (title: string, lines?: (string | null | undefined | false)[]) => () => void;
  /**
   * Report a failed request: an unreachable server at most every 15 s; the session stays
   * (rules/31). Returns true when the failure was that, so callers skip their own message.
   */
  reportUnreachable: (error: unknown) => boolean;
}

export const ToastContext = createContext<ToastValue | null>(null);

/** The admin screen's notices (provided by the admin shell). */
export function useToast(): ToastValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error('useToast must be used inside ToastProvider');
  return value;
}
