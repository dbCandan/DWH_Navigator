/** How a confirmation reads: the verb on its button, and whether the step loses something. */
export interface ConfirmOptions {
  /** The button that goes ahead ("Sil", "Pasifleştir"); "Onayla" when not given. */
  action?: string;
  /** The button that stays; "Vazgeç" when not given. */
  cancel?: string;
  /** A step that deletes or closes something: red button, the focus starts on "Vazgeç". */
  danger?: boolean;
}

export type ConfirmHandler = (text: string, options: ConfirmOptions) => boolean | Promise<boolean>;

let dialog: ConfirmHandler | null = null;
let override: ConfirmHandler | null = null;

/**
 * The admin shell's dialog answers `confirmAction` while it is mounted. Returns a function that
 * takes it back, only if it is still the answering one.
 */
export function provideConfirmDialog(next: ConfirmHandler): () => void {
  dialog = next;
  return () => {
    if (dialog === next) dialog = null;
  };
}

/** An answer in place of the dialog (a test's); `null` gives the dialog back. */
export function setConfirmHandler(next: ConfirmHandler | null): void {
  override = next;
}

/**
 * Ask before a step that cannot be taken back. The text's first line is the question, the rest
 * its explanation. Without the shell's dialog (outside the admin screens) the browser asks.
 */
export async function confirmAction(text: string, options: ConfirmOptions = {}): Promise<boolean> {
  const answer = override ?? dialog;
  return answer ? answer(text, options) : window.confirm(text);
}
