import {describe, expect, it} from 'vitest';
import globals from '../globals.css?raw';

/**
 * dictionary-explorer Requirement 17 and Decision 5, search-settings Decision 11: every color of
 * the source screens is a token in globals.css; components and pages write none of their own.
 */
const stylesheets = import.meta.glob<string>(['../**/*.css', '!../globals.css'], {
  eager: true,
  query: '?raw',
  import: 'default',
});
const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}', '!../test/**', '!../types/**'], {
  eager: true,
  query: '?raw',
  import: 'default',
});

const withoutComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '');

/** Color literals: hex, rgb()/rgba() and hsl()/hsla() whose saturation and lightness are numbers. */
function colorLiterals(text: string, named = true): string[] {
  const found: string[] = [];
  for (const match of text.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) found.push(match[0]);
  for (const match of text.matchAll(/\brgba?\(\s*\d[^)]*\)/g)) found.push(match[0]);
  for (const match of text.matchAll(/\bhsla?\(([^()]|\([^()]*\))*\)/g))
    if (/\d%/.test(match[0])) found.push(match[0]);
  if (named)
    for (const match of text.matchAll(/(?<![\w-])(white|black|red|green|blue|yellow|gray|grey)(?![\w-])/g))
      found.push(match[0]);
  return found;
}

describe('design tokens', () => {
  it('keeps every component and page stylesheet free of color literals', () => {
    expect(Object.keys(stylesheets).length).toBeGreaterThanOrEqual(2);
    for (const [path, css] of Object.entries(stylesheets)) {
      // Selector text such as #root or #hud is not a color; only declaration values count.
      const values = [...withoutComments(css).matchAll(/:\s*([^;{}]+)[;}]/g)].map((m) => m[1]).join('\n');
      expect(colorLiterals(values), path).toEqual([]);
    }
  });

  it('keeps component and library code free of color literals', () => {
    for (const [path, code] of Object.entries(sources)) {
      // A digit right after "rgba(" or a number with % inside "hsla(" is a literal; token
      // triplets and pairs filled in at runtime are not.
      expect(colorLiterals(code.replace(/\/\/.*$/gm, ''), false), path).toEqual([]);
    }
  });

  it('defines every token a stylesheet reads', () => {
    const defined = new Set([...globals.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
    expect(defined.size).toBeGreaterThan(150);
    for (const css of Object.values(stylesheets)) for (const match of css.matchAll(/(--[\w-]+)\s*:/g)) defined.add(match[1]);
    for (const [path, css] of Object.entries(stylesheets)) {
      const used = [...withoutComments(css).matchAll(/var\(\s*(--[\w-]+)/g)].map((m) => m[1]);
      // Set at runtime through the CSS object model: hero centring, dossier hue, row index, bar width.
      const runtime = new Set(['--shift-top', '--shift-bottom', '--hue', '--i', '--w', '--pad-b']);
      const missing = used.filter((name) => !defined.has(name) && !runtime.has(name));
      expect([...new Set(missing)], path).toEqual([]);
    }
  });

  it('applies a star cluster\'s computed hue with the token saturation and lightness', () => {
    const explorer = Object.entries(stylesheets).find(([path]) => path.endsWith('explorer/explorer.css'))?.[1] ?? '';
    const tones = [...explorer.matchAll(/hsla?\(([^()]|\([^()]*\))*\)/g)].map((m) => m[0]);
    expect(tones.length).toBeGreaterThan(5);
    for (const tone of tones) expect(tone).toMatch(/^hsla?\((var\(--hue\)|calc\(var\(--hue\) \+ \d+\)), var\(--cluster-[\w-]+\)\)$/);
  });
});
