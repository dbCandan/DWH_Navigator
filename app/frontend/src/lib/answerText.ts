/*
 * Pure text rules of the answer view, as the source page wrote them (index.html: pct,
 * breakable, verdictClass, splitSummary, conceptChip, richOf). The analyst's text is only ever
 * split into plain text, column names and table references; it is never read as HTML
 * (question-analysis Requirement 21).
 */
import type {AnalysisAnswer, AnswerObject} from '@/types/analysis';

/** A score 0..1 as a whole percent. */
export const pct = (x: number | null | undefined): number => Math.round((x || 0) * 100);

/**
 * The whole percent before the votes, when the votes moved the shown confidence
 * (answer-feedback Requirement 7, 12); null otherwise.
 */
export function movedBefore(m: Pick<AnswerObject, 'score' | 'score_before'>): number | null {
  if (m.score_before == null || pct(m.score_before) === pct(m.score)) return null;
  return pct(m.score_before);
}

/** Long identifiers may wrap only at CamelCase and underscore boundaries. */
export const breakParts = (name: string): string[] => name.split(/(?<=[a-z0-9])(?=[A-Z])|(?<=_)/);

/** "v-VAR", "v-KISMEN", "v-BULUNAMADI": the answer's colour class. */
export const verdictClass = (verdict: string | null | undefined): string => 'v-' + (verdict || '').split(' ')[0];

/** The card's element id, from the table key. */
export const cardId = (key: string): string => 'res-' + key.replace(/[^A-Za-z0-9_-]/g, '_');

/** The summary as a headline (its first sentence) and a lead (the rest). */
export function splitSummary(summary: string): [string, string] {
  const s = summary
    .replace(/^(KISMEN VAR|VAR|BULUNAMADI)\s*[.—–-]\s*/, '')
    .replace(/^[A-ZÇĞİÖŞÜ ]+ — /, '')
    .trim();
  const cut = s.search(/[.!?]\s+(?=[A-ZÇĞİÖŞÜ"“'])/);
  return cut > 30 ? [s.slice(0, cut + 1), s.slice(cut + 1).trim()] : [s, ''];
}

const CONCEPT_CLASS: Record<string, string> = {
  zaman: 'k-zaman',
  kırılım: 'k-kirilim',
  ölçü: 'k-olcu',
  'kırılım değeri': 'k-deger',
};

/** A concept "kind:label" as its chip: tone class, the "kind · " prefix and the label. */
export function conceptParts(concept: string): {cls: string; prefix: string; label: string} {
  const [kind, ...rest] = concept.split(':');
  const label = rest.join(':');
  return {
    cls: CONCEPT_CLASS[kind] ?? '',
    prefix: kind === 'terim' || kind === label ? '' : kind + ' · ',
    label,
  };
}

/** A note's scope as a tone: warnings amber, scope limits blue, derivations violet. */
export const NOTE_TONE: Record<string, string> = {
  Uyarı: 't-warn',
  'Veri kalitesi': 't-warn',
  Kapsam: 't-scope',
  Netleştirme: 't-ask',
  Türetme: 't-derive',
  'Top 5 dışı': 't-near',
  'Yakın aday': 't-near',
};

export type RichToken =
  | {kind: 'text'; text: string}
  /** A CamelCase column name, set in mono. */
  | {kind: 'column'; text: string}
  /** A table: its key, the short name shown and, when known, the suggestion it leads to. */
  | {kind: 'table'; key: string; name: string; object: AnswerObject | null; suggested: boolean};

const reEsc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Table and column names inside the analyst's prose (source richOf): a full `DB.Şema.Obje` key or
 * a known table name becomes a table reference, a CamelCase word a column name.
 */
export function richTokenizer(
  answer: Pick<AnalysisAnswer, 'objects' | 'near' | 'rejected'>,
  catalog: readonly {key: string; name: string}[] = [],
): (text: string) => RichToken[] {
  const known = new Map<string, AnswerObject>();
  for (const m of [...answer.objects, ...answer.near, ...(answer.rejected ?? [])]) {
    if (!known.has(m.key)) known.set(m.key, m);
    if (!known.has(m.name)) known.set(m.name, m);
  }
  // Every other table of the dictionary, by its full key and, when no other table shares it, by
  // its short name: the analyst also names tables it read and did not suggest (a warning).
  const others = new Map<string, string>();
  const nameCount = new Map<string, number>();
  for (const c of catalog) nameCount.set(c.name, (nameCount.get(c.name) ?? 0) + 1);
  for (const c of catalog) {
    if (known.has(c.key)) continue;
    others.set(c.key, c.key);
    if (nameCount.get(c.name) === 1 && !known.has(c.name)) others.set(c.name, c.key);
  }
  const names = [...new Set([...known.keys(), ...others.keys()].filter((k) => !k.includes('.')))]
    .sort((a, b) => b.length - a.length)
    .map(reEsc);
  const re = new RegExp(
    String.raw`\b(?:[A-Za-z]\w*\.[A-Za-z]\w*\.\w+` +
      (names.length ? '|' + names.join('|') : '') +
      String.raw`|[A-Z][a-z0-9]+(?:[A-Z]+[a-z0-9]*)+)\b`,
    'g',
  );
  const cards = new Set(answer.objects.map((m) => m.key));
  return (text) => {
    if (!text) return [];
    const out: RichToken[] = [];
    let at = 0;
    for (const hit of text.matchAll(re)) {
      const word = hit[0];
      const index = hit.index;
      if (index > at) out.push({kind: 'text', text: text.slice(at, index)});
      at = index + word.length;
      const full = word.split('.').length === 3;
      const m = known.get(word) ?? null;
      const other = m ? undefined : others.get(word);
      if (other !== undefined) {
        out.push({kind: 'table', key: other, name: other.split('.').pop() ?? other, object: null, suggested: false});
        continue;
      }
      if (!full && !m) {
        out.push({kind: 'column', text: word});
        continue;
      }
      out.push({
        kind: 'table',
        key: m ? m.key : word,
        name: m ? m.name : (word.split('.').pop() ?? word),
        object: m,
        suggested: m !== null && cards.has(m.key),
      });
    }
    if (at < text.length) out.push({kind: 'text', text: text.slice(at)});
    return unquoted(out);
  };
}

const QUOTES: Record<string, string> = {"'": "'", '"': '"', '‘': '’', '“': '”', '`': '`'};

/** A name the analyst put in quotes ('RecordingTime') is already set apart as a chip: the
 *  quotes around it go. */
function unquoted(tokens: RichToken[]): RichToken[] {
  for (let i = 1; i < tokens.length - 1; i++) {
    const before = tokens[i - 1];
    const after = tokens[i + 1];
    if (tokens[i].kind === 'text' || before.kind !== 'text' || after.kind !== 'text') continue;
    const open = before.text.at(-1) ?? '';
    const close = QUOTES[open];
    if (close === undefined || !after.text.startsWith(close)) continue;
    tokens[i - 1] = {kind: 'text', text: before.text.slice(0, -1)};
    tokens[i + 1] = {kind: 'text', text: after.text.slice(1)};
  }
  return tokens.filter((tk) => tk.kind !== 'text' || tk.text !== '');
}
