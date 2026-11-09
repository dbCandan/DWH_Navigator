/**
 * Whether this browser was already shown the main screen's welcome guide. The visitor is known
 * only by the device id this browser keeps in `localStorage` (003-anonymous-visitor Decision 1), so
 * the mark lives beside it and has the same lifetime: a browser that keeps its device id never sees
 * the guide again. The mark is written the moment the guide opens, so closing the tab half way
 * through still counts as seen.
 *
 * When the storage is closed nothing can be remembered; the guide then stays away rather than
 * opening on every page load.
 */
const KEY = 'dwhnavigator.welcome';
const SEEN = '1';

/** Set once the guide was shown in this page, even when the storage refuses the write. */
let shownInPage = false;

export function shouldShowWelcome(): boolean {
  if (shownInPage) return false;
  try {
    return localStorage.getItem(KEY) !== SEEN;
  } catch {
    return false;
  }
}

export function markWelcomeSeen(): void {
  shownInPage = true;
  try {
    localStorage.setItem(KEY, SEEN);
  } catch {
    // storage closed: the page remembers it until it is reloaded
  }
}

/** Tests that do not look at the guide keep it closed without writing to the browser storage. */
export function skipWelcomeForTests(): void {
  shownInPage = true;
}

/**
 * Tests start a case as a browser that never saw the guide, or with `keepStorage` as a reload of a
 * browser that already did.
 */
export function forgetWelcomeForTests({keepStorage = false}: {keepStorage?: boolean} = {}): void {
  shownInPage = false;
  if (keepStorage) return;
  try {
    localStorage.removeItem(KEY);
  } catch {
    // storage closed
  }
}
