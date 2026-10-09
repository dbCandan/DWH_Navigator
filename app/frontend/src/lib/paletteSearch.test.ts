import {describe, expect, it} from 'vitest';
import {filterPalette, scoreItem, type PaletteEntry} from './paletteSearch';

const entry = (groupId: string, title: string, subtitle = ''): PaletteEntry => ({
  groupId,
  group: groupId,
  icon: 'home',
  title,
  subtitle,
  run: () => undefined,
});

describe('command palette search (search-settings Requirement 22)', () => {
  // The typed words reach the scoring already folded (bakım → bakim).
  it('scores 3 per word in the title, 1 in the subtitle and 2 more when the title starts with it', () => {
    expect(scoreItem({title: 'Bakım', subtitle: 'Arama indeksi'}, ['bakim'])).toBe(5);
    expect(scoreItem({title: 'Genel bakış', subtitle: 'Bakım'}, ['bakis'])).toBe(3);
    expect(scoreItem({title: 'Genel bakış', subtitle: 'Arama indeksi'}, ['indeks'])).toBe(1);
    expect(scoreItem({title: 'Genel bakış', subtitle: ''}, ['genel', 'indeks'])).toBeNull();
  });

  it('folds Turkish letters and accents in titles and in the typed text', () => {
    expect(scoreItem({title: 'İŞLEM ÖZETİ'}, ['islem'])).toBe(5);
    expect(scoreItem({title: 'Yapay zekâ'}, ['zeka'])).toBe(3);
    expect(filterPalette([entry('pages', 'Kelimeler', 'Terim sözlüğü')], 'SÖZLÜĞÜ').map((e) => e.title)).toEqual(['Kelimeler']);
  });

  it('shows the pages and actions on an empty search, the best matches otherwise', () => {
    const entries = [
      entry('pages', 'Genel bakış', 'Sistem sağlığı'),
      entry('settings', 'BM25 k1', 'Arama ve cevap'),
      entry('actions', 'Uygulamaya dön', 'Soru sorma ekranı'),
      entry('pages', 'Arama ve cevap', 'Analistin okuduğu malzeme'),
    ];
    expect(filterPalette(entries, '  ').map((e) => e.title)).toEqual([
      'Genel bakış',
      'Uygulamaya dön',
      'Arama ve cevap',
    ]);
    expect(filterPalette(entries, 'arama').map((e) => e.title)).toEqual(['Arama ve cevap', 'BM25 k1']);
    expect(filterPalette(entries, 'yok böyle')).toEqual([]);
  });

  it('shows at most 60 results', () => {
    const many = Array.from({length: 80}, (_, i) => entry('tables', `vTable${i}`));
    expect(filterPalette(many, 'vtable')).toHaveLength(60);
  });
});
