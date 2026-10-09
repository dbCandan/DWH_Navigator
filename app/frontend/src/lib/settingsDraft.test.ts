import {describe, expect, it} from 'vitest';
import {searchSettings} from '@/test/admin';
import {adoptDraft, changedKeys, pageOfSection, sameValue, settingFields, showValue} from './settingsDraft';

describe('settings draft (search-settings Requirement 18, 23)', () => {
  it('shows a value as the source row did', () => {
    expect(showValue({format: 'pct', step: 0.05}, 0.55, 'boş')).toBe('%55');
    expect(showValue({format: null, step: 0.05}, 0.2, 'boş')).toBe('0.20');
    expect(showValue({format: null, step: 0.5}, 3, 'boş')).toBe('3.0');
    expect(showValue({format: null, step: 1}, 14, 'boş')).toBe('14');
    expect(showValue({format: null, step: null}, true, 'boş')).toBe('true');
    expect(showValue({format: null, step: null}, false, 'boş')).toBe('boş');
  });

  it('compares numbers with a tolerance and puts each section on its page', () => {
    expect(sameValue(0.1 + 0.2, 0.3)).toBe(true);
    expect(sameValue(true, 1)).toBe(false);
    expect(pageOfSection('search')).toBe('arama');
    expect(pageOfSection('data')).toBe('bakim');
    const fields = settingFields(searchSettings());
    expect(fields.get('cache.enabled')).toMatchObject({page: 'bakim', section: 'Önceki cevaplar'});
  });

  it('keeps unsaved edits when new values arrive and lists the changed keys in schema order', () => {
    const before = searchSettings();
    const form = {...before.values, 'search.bm25.k1': 1.5, 'analyst.shortlist': 20};
    expect(changedKeys(before, form)).toEqual(['analyst.shortlist', 'search.bm25.k1']);
    const after = searchSettings({'cache.max_age_days': 7, 'analyst.shortlist': 18});
    const adopted = adoptDraft(before, form, after);
    expect(adopted).toMatchObject({'analyst.shortlist': 20, 'search.bm25.k1': 1.5, 'cache.max_age_days': 7});
    expect(adoptDraft(null, form, after)).toEqual(after.values);
  });
});
