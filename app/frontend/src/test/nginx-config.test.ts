import {describe, expect, it} from 'vitest';
import headers from '../../nginx.security-headers.conf?raw';
import server from '../../nginx.release.conf?raw';

/** user-accounts Requirement 14: the front-end server's page policy and headers, verbatim. */
describe('front-end server configuration', () => {
  const header = (name: string) => new RegExp(`^add_header ${name} "([^"]*)" always;$`, 'm').exec(headers)?.[1];

  it('sends the strict page policy, word for word', () => {
    expect(header('Content-Security-Policy')).toBe(
      "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    );
    expect(headers).not.toMatch(/unsafe-inline|unsafe-eval/);
  });

  it('sends the same security headers as the backend', () => {
    expect(header('X-Content-Type-Options')).toBe('nosniff');
    expect(header('X-Frame-Options')).toBe('DENY');
    expect(header('X-Permitted-Cross-Domain-Policies')).toBe('none');
    expect(header('Referrer-Policy')).toBe('no-referrer');
    expect(header('Cross-Origin-Opener-Policy')).toBe('same-origin');
    expect(header('Cross-Origin-Embedder-Policy')).toBe('require-corp');
    expect(header('Cross-Origin-Resource-Policy')).toBe('same-origin');
    expect(header('Permissions-Policy')).toBe('camera=(), microphone=(), geolocation=(), payment=(), usb=()');
    expect(header('Strict-Transport-Security')).toBe('max-age=31536000');
  });

  it('hides the server version and caches only content-hashed build files', () => {
    expect(server).toMatch(/^\s*server_tokens off;$/m);
    const locations = [...server.matchAll(/location ([^{]+)\{([^}]*)\}/g)].map((m) => [m[1].trim(), m[2]] as const);
    expect(locations.map(([path]) => path)).toEqual(['/assets/', '/']);
    for (const [, body] of locations) expect(body).toContain('include /etc/nginx/conf.d/security-headers.conf;');
    expect(locations[0][1]).toContain('add_header Cache-Control "public, max-age=31536000, immutable" always;');
    expect(locations[1][1]).toContain('add_header Cache-Control "no-store" always;');
  });
});
