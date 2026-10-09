import {describe, expect, it} from 'vitest';
import {formatDuration, formatKilo} from './format';
import {message} from '@/test/render';

const t = (key: string, values?: Record<string, string | number>) => message(key, values);

describe('durations as the admin screen writes them (admin.html msText)', () => {
  it.each([
    [0, '0 ms'],
    [850.4, '850 ms'],
    [2400, '2,4 sn'],
    [12345, '12 sn'],
    [185000, '3 dk 05 sn'],
  ])('%d ms reads "%s"', (ms, text) => {
    expect(formatDuration(ms, t)).toBe(text);
  });
});

describe('token counts as the admin screen writes them (admin.html kilo)', () => {
  it.each([
    [0, '0'],
    [950, '950'],
    [12345, '12,3 k'],
    [1234567, '1,2 M'],
  ])('%d reads "%s"', (n, text) => {
    expect(formatKilo(n, t)).toBe(text);
  });
});
