/** The `.xlsx` media type an upload is sent with (dictionary-management Requirement 2). */
export const XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** Only `.xlsx` files are sent; anything else is refused before a request (Requirement 15). */
export function isWorkbookName(name: string): boolean {
  return /\.xlsx$/i.test(name);
}

/**
 * An upload request: the workbook itself is the body, its name travels percent-encoded in
 * `X-Filename` (dictionary-management Decision 10; vocabulary-management Requirement 7).
 */
export function workbookUpload(file: File): RequestInit {
  return {
    method: 'POST',
    body: file,
    headers: {'Content-Type': XLSX_MEDIA_TYPE, 'X-Filename': encodeURIComponent(file.name)},
  };
}
