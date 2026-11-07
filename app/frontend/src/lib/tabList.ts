/**
 * The term list this browser tab started or last saw (list-search Decision 15): only the list's
 * public id, in the tab's own session storage, so a reload stays on the same list and a fresh
 * tab opens empty. No file name, header or term text is kept; storage that is blocked or full
 * makes the tab simply forget.
 */
const KEY = 'dwhnavigator.list';

export function rememberTabList(id: string): void {
  try {
    sessionStorage.setItem(KEY, id);
  } catch {
    // storage blocked: a reload opens the page empty
  }
}

export function recallTabList(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Forget the tab's list; with `id`, only when it is still that list. */
export function forgetTabList(id?: string): void {
  try {
    if (id === undefined || sessionStorage.getItem(KEY) === id) sessionStorage.removeItem(KEY);
  } catch {
    // nothing to forget
  }
}
