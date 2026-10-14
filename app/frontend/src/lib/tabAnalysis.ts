/**
 * The question this browser tab started (question-analysis Requirement 19, Decision 26): only the
 * job's public `analysis_id`, in the tab's own session storage, so a reload follows the same job
 * and another tab never takes it over. No question text, token or personal data is kept; storage
 * that is blocked or full makes the tab simply forget.
 */
const KEY = 'dwhnavigator.analysis';

export function rememberTabAnalysis(id: string): void {
  try {
    sessionStorage.setItem(KEY, id);
  } catch {
    // storage blocked: a reload opens the page empty
  }
}

export function recallTabAnalysis(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Forget the tab's question; with `id`, only when it is still that job. */
export function forgetTabAnalysis(id?: string): void {
  try {
    if (id === undefined || sessionStorage.getItem(KEY) === id) sessionStorage.removeItem(KEY);
  } catch {
    // nothing to forget
  }
}
