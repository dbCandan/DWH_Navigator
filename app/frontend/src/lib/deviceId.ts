/**
 * The browser's device id (application-foundation 003-anonymous-visitor Requirement 2,
 * Decision 1): a random UUID 4 made once with the browser's cryptographic generator and kept in
 * `localStorage`, sent as `X-Device-Id` with every main-screen request. It is not a credential and
 * never goes into an address. When the storage is closed the id lives for the page only.
 */
const KEY = 'dwhnavigator.device';
const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

let current: string | null = null;

function stored(): string | null {
  try {
    const value = localStorage.getItem(KEY);
    return value !== null && UUID4.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function deviceId(): string {
  if (current !== null) return current;
  current = stored() ?? crypto.randomUUID();
  try {
    localStorage.setItem(KEY, current);
  } catch {
    // storage closed: the id stays in memory for this page
  }
  return current;
}

/** Tests start each case without the id read earlier. */
export function forgetDeviceIdForTests(): void {
  current = null;
}
