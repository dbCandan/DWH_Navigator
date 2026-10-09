import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, writeSession} from './authStorage';
import {attachmentName, downloadFile} from './download';
import type {AuthenticatedUser} from '@/types/auth';

describe('file downloads (user-accounts Requirement 12)', () => {
  beforeEach(() => writeSession('token', {username: 'u', tenant_id: 't'} as AuthenticatedUser));
  afterEach(() => {
    vi.restoreAllMocks();
    clearAuth();
  });

  it('fetches the file with the token in a header and saves the blob under the server name', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['xlsx']), {
        status: 200,
        headers: {'Content-Disposition': "attachment; filename=\"x.xlsx\"; filename*=UTF-8''s%C3%B6zl%C3%BCk.xlsx"},
      }),
    );
    const createObjectURL = vi.fn(() => 'blob:local/1');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, {createObjectURL, revokeObjectURL}));
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this);
    });

    const name = await downloadFile('/admin/dictionary/export', 'sozluk.xlsx');

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/dwhnavigator/v1/admin/dictionary/export');
    expect(String(url)).not.toContain('token');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer token');
    expect(name).toBe('sözlük.xlsx');
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(clicked[0].download).toBe('sözlük.xlsx');
    expect(clicked[0].href).toBe('blob:local/1');
    expect(clicked[0].isConnected).toBe(false);
  });

  it('reads the attachment name and never a path', () => {
    expect(attachmentName('attachment; filename="rapor.xlsx"')).toBe('rapor.xlsx');
    expect(attachmentName('attachment; filename=rapor.xlsx')).toBe('rapor.xlsx');
    expect(attachmentName('attachment; filename="../../etc/passwd"')).toBe('passwd');
    expect(attachmentName('attachment; filename=".."')).toBeNull();
    expect(attachmentName(null)).toBeNull();
  });
});
