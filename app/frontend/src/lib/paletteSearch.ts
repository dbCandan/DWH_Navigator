import type {IconName} from '@/components/admin/Icon';
import {fold} from '@/lib/fold';

export interface PaletteEntry {
  /** Stable group id; `pages` and `actions` show on an empty search (search-settings Requirement 22). */
  groupId: string;
  /** Group title: "Sayfalar", "İşlemler", ... */
  group: string;
  icon: IconName;
  title: string;
  subtitle?: string;
  run: () => void;
}

const RESTING_GROUPS = new Set(['pages', 'actions']);
const LIMIT = 60;

/**
 * Score an item for the typed words: every word must appear in the title or the subtitle; a
 * word scores 3 in the title or 1 in the subtitle, plus 2 when the title starts with it. Null when
 * the item does not match.
 */
export function scoreItem(item: Pick<PaletteEntry, 'title' | 'subtitle'>, words: readonly string[]): number | null {
  const title = fold(item.title);
  const haystack = fold(item.title + ' ' + (item.subtitle ?? ''));
  if (!words.every((word) => haystack.includes(word))) return null;
  return words.reduce((sum, word) => sum + (title.includes(word) ? 3 : 1) + (title.startsWith(word) ? 2 : 0), 0);
}

/** The items to show for a query: the resting groups when empty, else the best 60 matches. */
export function filterPalette(entries: readonly PaletteEntry[], query: string): PaletteEntry[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return entries.filter((entry) => RESTING_GROUPS.has(entry.groupId)).slice(0, LIMIT);
  return entries
    .map((entry) => [entry, scoreItem(entry, words)] as const)
    .filter((pair): pair is readonly [PaletteEntry, number] => pair[1] !== null)
    .sort((a, b) => b[1] - a[1])
    .map(([entry]) => entry)
    .slice(0, LIMIT);
}
