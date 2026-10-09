import {apiFetch} from '@/lib/apiClient';

/**
 * File downloads (Excel reports, dictionary export and template) go through the shared client
 * with the access token in the `Authorization` header; the file arrives as a blob and the
 * browser saves it. A plain link would carry no token, and the token never travels in an
 * address (user-accounts Requirement 12).
 */
export async function downloadFile(path: string, fallbackName: string, init: RequestInit = {}): Promise<string> {
  const response = await apiFetch(path, init);
  const name = attachmentName(response.headers.get('Content-Disposition')) ?? fallbackName;
  saveBlob(await response.blob(), name);
  return name;
}

/** The file name of an `attachment` disposition: RFC 6266 `filename*` first, then `filename`. */
export function attachmentName(disposition: string | null): string | null {
  if (!disposition) return null;
  const extended = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(disposition)?.[1];
  if (extended) {
    try {
      return safeName(decodeURIComponent(extended.trim()));
    } catch {
      // A malformed escape falls back to the plain name below.
    }
  }
  const plain = /filename\s*=\s*"([^"]*)"|filename\s*=\s*([^;]+)/.exec(disposition);
  const value = plain?.[1] ?? plain?.[2]?.trim();
  return value ? safeName(value) : null;
}

/** Keep the last path segment only: a server-sent name cannot point into another folder. */
function safeName(name: string): string | null {
  const last = name.split(/[\\/]/).pop()?.trim() ?? '';
  return last && last !== '.' && last !== '..' ? last : null;
}

/** Hand a blob to the browser's save flow through a short-lived object address. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
