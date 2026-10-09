import type {SearchSettings, SearchSettingField, SearchSettingSection, SettingValue, SettingValues} from '@/types/search';

/** The admin page a settings section is shown on (admin.html PAGE_OF_SECTION). */
export type SettingsPage = 'arama' | 'bakim';

export const pageOfSection = (page: SearchSettingSection['page']): SettingsPage => (page === 'search' ? 'arama' : 'bakim');

/** A field with the page and the section title it is shown under. */
export interface SettingField extends SearchSettingField {
  page: SettingsPage;
  section: string;
}

export function settingFields(settings: SearchSettings): Map<string, SettingField> {
  const fields = new Map<string, SettingField>();
  for (const section of settings.sections)
    for (const field of section.fields)
      fields.set(field.key, {...field, page: pageOfSection(section.page), section: section.title});
  return fields;
}

/** A section's fields with their page and section, as the rows need them. */
export function sectionFields(settings: SearchSettings, section: SearchSettingSection): SettingField[] {
  const fields = settingFields(settings);
  return section.fields.map((field) => fields.get(field.key)).filter((field): field is SettingField => field !== undefined);
}

export const sameValue = (a: SettingValue | undefined, b: SettingValue | undefined) =>
  typeof a === 'number' && typeof b === 'number' ? Math.abs(a - b) < 1e-9 : a === b;

/** The keys whose draft value differs from the saved one, in schema order. */
export function changedKeys(settings: SearchSettings, form: SettingValues): string[] {
  return settings.sections.flatMap((section) =>
    section.fields.map((field) => field.key).filter((key) => !sameValue(form[key], settings.values[key])),
  );
}

/**
 * New values from the server: edits not saved yet stay in the draft (search-settings
 * Requirement 23; admin.html Settings.adopt).
 */
export function adoptDraft(previous: SearchSettings | null, form: SettingValues, next: SearchSettings): SettingValues {
  const draft: SettingValues = {...next.values};
  if (previous === null) return draft;
  for (const key of changedKeys(previous, form)) if (key in next.values) draft[key] = form[key];
  return draft;
}

/**
 * A value as the row shows it (admin.html Settings.show): `%NN` for a percentage, two decimals
 * when the step is below 0.1, one below 1, else the plain number; any other value as it is, an
 * empty or false one as `empty` ("boş"), as the source's reset tooltip wrote it.
 */
export function showValue(
  field: Pick<SearchSettingField, 'format' | 'step'>,
  value: SettingValue | undefined,
  empty: string,
): string {
  if (field.format === 'pct') return `%${Math.round(Number(value) * 100)}`;
  if (typeof value === 'number')
    return field.step && field.step < 1 ? Number(value).toFixed(field.step < 0.1 ? 2 : 1) : String(value);
  return value ? String(value) : empty;
}
