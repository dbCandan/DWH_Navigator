/**
 * The "Evren" map's layout: pure and deterministic (dictionary-explorer Requirement 4). The same
 * galaxy data always gives the same positions, sizes, depths, twinkle phases and tones. It is the
 * source's `Cosmos.build` and `screen` computation (index.html), unchanged.
 */

/** One table as the galaxy endpoint returns it (Requirement 3). */
export interface GalaxyItem {
  key: string;
  name: string;
  schema: string;
  group: string;
  columns: number;
}

export interface Cluster {
  name: string;
  /** Centre in unit coordinates (-1..1) before rotation. */
  x: number;
  y: number;
  hue: number;
  n: number;
  members: Star[];
}

export interface Star extends GalaxyItem {
  g: Cluster;
  x: number;
  y: number;
  /** Depth 0.35..1: nearer stars are brighter, bigger, turn and drift more. */
  z: number;
  size: number;
  /** Twinkle phase. */
  tw: number;
  hue: number;
  /** Last drawn screen position. */
  sx: number;
  sy: number;
}

export interface Dust {
  x: number;
  y: number;
  z: number;
  tw: number;
}

export interface Galaxy {
  stars: Star[];
  clusters: Cluster[];
  byKey: Map<string, Star>;
  dust: Dust[];
}

/** FNV-1a over the text's characters (code units of each code point's first unit, as the source). */
export function fnv1a(text: string): number {
  let h = 2166136261;
  for (const c of text) {
    h ^= c.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** The source's small seeded generator: the same seed gives the same sequence in 0..1. */
export function seeded(seed: number): () => number {
  let state = seed;
  return () =>
    ((state = Math.imul(state ^ (state >>> 15), 2246822507) ^ Math.imul(state ^ (state >>> 13), 3266489909)) >>> 0) /
    4294967296;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
export const DUST_COUNT = 480;

/**
 * Build the galaxy: every table a star, every group a cluster. Clusters are ordered by member
 * count (largest first) and placed on a sunflower spiral from the centre outwards; a cluster's
 * hue is its name's FNV-1a modulo 360; members spiral around the centre in the input (name)
 * order, with small offsets, depth and twinkle phase from a seed derived from the cluster name.
 */
export function buildGalaxy(items: readonly GalaxyItem[]): Galaxy {
  const byGroup = new Map<string, GalaxyItem[]>();
  for (const item of items) {
    const members = byGroup.get(item.group);
    if (members) members.push(item);
    else byGroup.set(item.group, [item]);
  }
  const ordered = [...byGroup.entries()].sort((a, b) => b[1].length - a[1].length);
  const count = ordered.length;
  const stars: Star[] = [];
  const byKey = new Map<string, Star>();
  const clusters = ordered.map(([name, members], gi): Cluster => {
    const r = 0.1 + 0.82 * Math.sqrt((gi + 0.5) / count);
    const a = gi * GOLDEN_ANGLE;
    const hue = fnv1a(name) % 360;
    const cluster: Cluster = {name, x: Math.cos(a) * r, y: Math.sin(a) * r, hue, n: members.length, members: []};
    const random = seeded(fnv1a(name));
    members.forEach((member, j) => {
      const rr = 0.018 + 0.022 * Math.sqrt(j) + random() * 0.012;
      const aa = j * GOLDEN_ANGLE + random() * 0.8;
      const star: Star = {
        ...member,
        g: cluster,
        x: cluster.x + Math.cos(aa) * rr,
        y: cluster.y + Math.sin(aa) * rr,
        z: 0.35 + random() * 0.65,
        size: 0.9 + Math.sqrt(member.columns) * 0.32,
        tw: random() * Math.PI * 2,
        hue,
        sx: 0,
        sy: 0,
      };
      stars.push(star);
      byKey.set(member.key, star);
      cluster.members.push(star);
    });
    return cluster;
  });
  const random = seeded(7);
  const dust = Array.from({length: DUST_COUNT}, () => ({x: random() * 2 - 1, y: random() * 2 - 1, z: random(), tw: random() * 6.3}));
  return {stars, clusters, byKey, dust};
}

/** What the screen position of a point depends on besides the point itself. */
export interface View {
  /** Sky rotation in radians (scaled by each star's depth). */
  rot: number;
  width: number;
  height: number;
  /** Smoothed pointer position, 0..1 across the window. */
  mouseX: number;
  mouseY: number;
  /** Camera offset in pixels (a selected star glides into the free space). */
  camX: number;
  camY: number;
}

/** Screen position: proportional to the window (47 % of its width, 46 % of its height). */
export function project(point: {x: number; y: number; z: number}, view: View): [number, number] {
  const c = Math.cos(view.rot * point.z);
  const s = Math.sin(view.rot * point.z);
  const x = point.x * c - point.y * s;
  const y = point.x * s + point.y * c;
  const px = (view.mouseX - 0.5) * 60 * point.z;
  const py = (view.mouseY - 0.5) * 40 * point.z;
  return [view.width / 2 + x * view.width * 0.47 + px + view.camX, view.height / 2 + y * view.height * 0.46 + py + view.camY];
}

/** Pointer selection radius in pixels (Requirement 6). */
export const PICK_RADIUS = 14;

/** The drawn star nearest to the point within 14 pixels, or null. */
export function nearestStar(stars: readonly Star[], x: number, y: number): Star | null {
  let best: Star | null = null;
  let bestDistance = PICK_RADIUS * PICK_RADIUS;
  for (const star of stars) {
    const d = (star.sx - x) ** 2 + (star.sy - y) ** 2;
    if (d < bestDistance) {
      bestDistance = d;
      best = star;
    }
  }
  return best;
}

const lowerTurkish = (text: string) => text.toLocaleLowerCase('tr-TR').replace(/ı/g, 'i');

/**
 * The one table whose name (vCustomerInfo), Schema.name or full key is exactly `text`, ignoring
 * case with ı and i equal; null when the text holds a space or when none or several match
 * (vCampaign in two schemas). Requirement 9.
 */
export function findTable(stars: readonly Star[], text: string): Star | null {
  const wanted = lowerTurkish(text.trim());
  if (!wanted || /\s/.test(wanted)) return null;
  const hits = stars.filter((star) => {
    const key = lowerTurkish(star.key);
    return key === wanted || key.endsWith('.' + wanted);
  });
  return hits.length === 1 ? hits[0] : null;
}
