/**
 * The "Evren" map: the source's `Cosmos` (index.html) on a canvas behind the page.
 * dictionary-explorer Requirement 5-8 and 14.
 *
 * The drawing, the frame budget (about 30 frames a second, 20 while reading or waiting), the
 * pointer behaviour and the voyage phases are the source's. The map moves whatever the system's
 * "reduce motion" preference says (Requirement 8, Decision 8).
 */
import {buildGalaxy, findTable, nearestStar, project, type Galaxy, type GalaxyItem, type Star, type View} from './layout';
import {hsla, rgba, type CosmosPalette} from './palette';

/** A candidate or result table with its score (0..1) when the search gave one. */
export interface ScoredTable {
  key: string;
  name: string;
  score?: number | null;
}

export interface CosmosHooks {
  /** "<tables> tablo · <clusters> küme" for the HUD. */
  onCount: (tables: number, clusters: number) => void;
  /** The voyage log line ("" clears it). */
  onLog: (text: string) => void;
  /** The pointer is over a star (null when not). */
  onHover: (star: Star | null, clientX: number, clientY: number) => void;
  /** A click on a star. */
  onStarClick: (key: string) => void;
  /** A click on the empty sky while a star is selected. */
  onSkyClick: () => void;
  /** Where the voyage starts: under the visible search field (null: no field on screen). */
  searchOrigin: () => [number, number] | null;
  /** Width of the open table panel, 0 when closed. */
  panelWidth: () => number;
  /** Whether the pointer target keeps the stars from being picked. */
  blocked: (target: Element) => boolean;
  /** Catalog messages. */
  text: (key: string, values?: Record<string, string | number>) => string;
}

type Mode = 'idle' | 'plan' | 'travel' | 'read' | 'wait' | 'final' | 'done';
type RoutePoint = {n: Star} | {xy: [number, number]};

// The radar opens every search: its beam turns RADAR_TURNS times before the voyage moves on.
// Candidates and answers that arrive earlier wait for it.
const RADAR_SPEED = 1.2; // rad/s
const RADAR_TURNS = 1;
export const RADAR_MS = ((RADAR_TURNS * 2 * Math.PI) / RADAR_SPEED) * 1000;
const SHIP_PACE = 0.81; // every route speed below is scaled by this
const TAU = 6.2832;

const fmt = (n: number) => n.toLocaleString('tr-TR');

export class CosmosEngine {
  private readonly ctx: CanvasRenderingContext2D;
  private width = 0;
  private height = 0;
  private dpr = 1;
  private running = false;
  private raf = 0;
  private galaxy: Galaxy | null = null;
  private rot = 0;
  private t = 0;
  private last = 0;
  private focusList: ScoredTable[] = [];
  private focusAt = 0;
  private hover: Star | null = null;
  private readonly mouse = {x: 0.5, y: 0.5, sx: 0.5, sy: 0.5};
  private selected: Star | null = null;
  private selectedAt = 0;
  private readonly cam = {x: 0, y: 0};
  // voyage state
  private mode: Mode = 'idle';
  private modeAt = 0;
  private readExpected = false;
  private shortlist = 8;
  private origin: [number, number] = [0, 0];
  private route: RoutePoint[] = [];
  private routeAt = 0;
  private dist = 0;
  private lastAlong = 0;
  private speed = 0;
  private loop = false;
  private arrived: number[] = [];
  private trail: [number, number][] = [];
  private candidateList: ScoredTable[] = [];
  private hudSteps: string[] = [];
  private reading: Star | null = null;
  private landedAt = 0;
  private pendingCandidates: ScoredTable[] | null = null;
  private pendingFocus: [ScoredTable[], string | undefined] | null = null;
  private pendingEnd = false;
  private readonly detach: () => void;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly palette: CosmosPalette,
    private readonly hooks: CosmosHooks,
  ) {
    const ctx = canvas.getContext('2d');
    if (ctx === null) throw new Error('canvas 2d context unavailable');
    this.ctx = ctx;
    const move = (e: PointerEvent) => this.pointerMove(e);
    const click = (e: MouseEvent) => this.click(e);
    const resize = () => {
      if (!this.running) return;
      this.resize();
    };
    const visibility = () => {
      if (!this.running) return;
      cancelAnimationFrame(this.raf);
      if (!document.hidden) this.raf = requestAnimationFrame(this.frame);
    };
    window.addEventListener('pointermove', move, {passive: true});
    window.addEventListener('resize', resize);
    document.addEventListener('click', click);
    document.addEventListener('visibilitychange', visibility);
    this.detach = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('resize', resize);
      document.removeEventListener('click', click);
      document.removeEventListener('visibilitychange', visibility);
    };
  }

  /** True when the map is drawn and has data. */
  get active(): boolean {
    return this.running && this.galaxy !== null;
  }

  get radarMs(): number {
    return RADAR_MS;
  }

  start(): void {
    this.running = true;
    this.resize();
    this.last = performance.now();
    cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame(this.frame);
  }

  destroy(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
    this.detach();
  }

  /** Lay out the galaxy (again, when the dictionary changed); an open selection is kept by key. */
  load(items: readonly GalaxyItem[]): void {
    const selectedKey = this.selected?.key ?? null;
    this.galaxy = buildGalaxy(items);
    this.selected = selectedKey ? (this.galaxy.byKey.get(selectedKey) ?? null) : null;
    this.hover = null;
    this.hooks.onCount(this.galaxy.stars.length, this.galaxy.clusters.length);
  }

  /** The one table matching a typed name (Requirement 9); null without the map. */
  find(text: string): Star | null {
    return this.galaxy ? findTable(this.galaxy.stars, text) : null;
  }

  node(key: string): Star | null {
    return this.galaxy?.byKey.get(key) ?? null;
  }

  /** Mark a star as the open table's (null clears); returns its node. */
  select(key: string | null): Star | null {
    const star = key ? (this.galaxy?.byKey.get(key) ?? null) : null;
    if (star !== this.selected) {
      this.selected = star;
      this.selectedAt = this.t;
    }
    return star;
  }

  /** A search starts: plot a route out of the search field. */
  begin({read = false, columns = 0, shortlist = 8}: {read?: boolean; columns?: number; shortlist?: number} = {}): void {
    this.origin = this.searchOrigin();
    this.mode = 'plan';
    this.modeAt = this.t;
    this.readExpected = read;
    this.shortlist = shortlist;
    this.route = [];
    this.trail = [];
    this.candidateList = [];
    this.focusList = [];
    this.reading = null;
    this.hudSteps = [];
    this.pendingCandidates = null;
    this.pendingFocus = null;
    this.pendingEnd = false;
    this.log(columns ? this.hooks.text('explorer.voyage.scanningColumns', {columns: fmt(columns)}) : this.hooks.text('explorer.voyage.planning'));
  }

  /**
   * The analysis waits in the queue: the voyage log says "sırada" once, without a count or a
   * time (question-analysis Requirement 20, Decision 22).
   */
  queued(): void {
    const step = this.hooks.text('explorer.voyage.queued');
    if (this.hudSteps.includes(step)) return;
    this.log(step);
  }

  /** Real candidate tables (model-free search): the route runs through them. */
  candidates(list: ScoredTable[]): void {
    if (!this.active || (this.mode !== 'plan' && this.mode !== 'travel')) return;
    if (this.mode === 'plan' && this.t - this.modeAt < RADAR_MS) {
      this.pendingCandidates = list;
      return;
    }
    this.showCandidates(list);
  }

  /** Final answer: fly to it, landing on the first; the results stay as a constellation. */
  focus(list: ScoredTable[], query?: string): void {
    if (this.mode === 'plan' && this.t - this.modeAt < RADAR_MS && this.active) {
      this.pendingFocus = [list, query];
      return;
    }
    this.showFocus(list, query);
  }

  /** Search finished without results, stopped or failed: stand down. */
  end(): void {
    if (this.mode === 'plan' && this.t - this.modeAt < RADAR_MS) {
      this.pendingEnd = true;
      return;
    }
    if (['plan', 'travel', 'read', 'wait'].includes(this.mode)) {
      this.mode = 'idle';
      this.route = [];
    }
  }

  // --------------------------------------------------------------- internals

  private log(step: string | null, replaceLast = false): void {
    if (replaceLast) this.hudSteps.pop();
    if (step) this.hudSteps.push(step);
    const shown = this.hudSteps.slice(-4); // the voyage log: latest steps only
    const separator = this.hooks.text('explorer.voyage.separator');
    const more = this.hudSteps.length > shown.length ? this.hooks.text('explorer.voyage.more') + separator : '';
    this.hooks.onLog(more + shown.join(separator));
  }

  private view(): View {
    return {
      rot: this.rot,
      width: this.width,
      height: this.height,
      mouseX: this.mouse.sx,
      mouseY: this.mouse.sy,
      camX: this.cam.x,
      camY: this.cam.y,
    };
  }

  private screen(point: {x: number; y: number; z: number}): [number, number] {
    return project(point, this.view());
  }

  private searchOrigin(): [number, number] {
    return this.hooks.searchOrigin() ?? [this.width / 2, 140];
  }

  private resize(): void {
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.width = document.documentElement.clientWidth;
    this.height = document.documentElement.clientHeight;
    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  private readonly frame = (now: number): void => {
    if (!this.running) return;
    this.raf = requestAnimationFrame(this.frame);
    // The chat model shares the (integrated) GPU with the browser: keep the sky light.
    const budget = this.mode === 'read' || this.mode === 'wait' ? 50 : 33;
    if (now - this.last < budget) return;
    // Real time, so the voyage keeps pace even when frames are sparse; capped only to avoid a
    // jump after the tab was in the background.
    const dt = Math.min(1000, now - this.last);
    this.last = now;
    this.t += dt;
    if (this.mode === 'idle' || this.mode === 'done') this.rot += dt * 0.000018;
    this.mouse.sx += (this.mouse.x - this.mouse.sx) * 0.05;
    this.mouse.sy += (this.mouse.y - this.mouse.sy) * 0.05;
    this.steer(dt);
    this.step(dt);
    this.draw();
  };

  private steer(dt: number): void {
    const panel = this.hooks.panelWidth();
    let tx = 0;
    let ty = 0;
    if (this.selected && this.width - panel > 320) {
      // phones: the panel covers the sky, no need to move it
      const [x, y] = this.screen(this.selected);
      tx = this.cam.x + ((this.width - panel - 12) / 2 - x);
      ty = this.cam.y + (this.height / 2 - y);
    }
    const k = 1 - Math.pow(0.94, dt / 16);
    this.cam.x += (tx - this.cam.x) * k;
    this.cam.y += (ty - this.cam.y) * k;
  }

  private point(p: RoutePoint): [number, number] {
    return 'n' in p ? [p.n.sx, p.n.sy] : p.xy;
  }

  // --------------------------------------------------------------- route geometry

  /** Nearest-neighbour ordering: a short, readable path. */
  private tour(from: [number, number], list: Star[]): Star[] {
    const rest = [...list];
    const out: Star[] = [];
    let [cx, cy] = from;
    while (rest.length) {
      let bi = 0;
      let bd = Infinity;
      rest.forEach((n, i) => {
        const d = (n.sx - cx) ** 2 + (n.sy - cy) ** 2;
        if (d < bd) {
          bd = d;
          bi = i;
        }
      });
      const n = rest.splice(bi, 1)[0];
      out.push(n);
      cx = n.sx;
      cy = n.sy;
    }
    return out;
  }

  private setRoute(points: RoutePoint[], pxPerSec: number, closed = false): void {
    this.route = points;
    this.dist = 0;
    this.lastAlong = 0;
    this.speed = pxPerSec * SHIP_PACE;
    this.loop = closed;
    this.routeAt = this.t;
    this.arrived = points.map(() => 0);
  }

  private lengths(): {pts: [number, number][]; cum: number[]; total: number} {
    const pts = this.route.map((p) => this.point(p));
    if (this.loop && pts.length > 1) pts.push(pts[1]);
    const cum = [0];
    for (let i = 1; i < pts.length; i++)
      cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    return {pts, cum, total: cum[cum.length - 1]};
  }

  private at(pts: [number, number][], cum: number[], d: number): [number, number, number] {
    let i = 1;
    while (i < cum.length - 1 && cum[i] < d) i++;
    const seg = cum[i] - cum[i - 1] || 1;
    const k = Math.max(0, Math.min(1, (d - cum[i - 1]) / seg));
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    return [x0 + (x1 - x0) * k, y0 + (y1 - y0) * k, Math.atan2(y1 - y0, x1 - x0)];
  }

  /** Distance along the route; a closed loop circles the finalists and never returns to the start. */
  private along(cum: number[], total: number): number {
    if (!this.loop || this.dist <= cum[1]) return Math.min(this.dist, total);
    return cum[1] + ((this.dist - cum[1]) % Math.max(1, total - cum[1]));
  }

  private shipPos(): [number, number] {
    if (!this.route.length) return this.origin;
    const {pts, cum, total} = this.lengths();
    if (pts.length < 2) return pts[0];
    const [x, y] = this.at(pts, cum, this.along(cum, total));
    return [x, y];
  }

  private step(dt: number): void {
    if (this.mode === 'plan' && this.t - this.modeAt >= RADAR_MS) this.radarDone();
    if (!this.route.length || !['travel', 'read', 'final'].includes(this.mode)) return;
    if (this.t - this.routeAt < (this.mode === 'final' ? 150 : 500)) return; // the route is drawn first
    const {cum, total} = this.lengths();
    this.dist += (this.speed * dt) / 1000;
    const d = this.along(cum, total);
    if (d < this.lastAlong) this.arrived.fill(0); // a new lap around the finalists
    this.lastAlong = d;
    for (let k = 1; k < this.route.length; k++) if (!this.arrived[k] && d >= cum[k] - 0.5) this.arrived[k] = this.t;
    if (this.mode === 'read') {
      const idx = Math.max(1, cum.findIndex((c) => c > d) - 1);
      const p = this.route[Math.min(idx, this.route.length - 1)];
      const n = 'n' in p ? p.n : null;
      if (n && n !== this.reading) {
        this.reading = n;
        const prefix = this.hooks.text('explorer.voyage.reading', {name: ''});
        this.log(this.hooks.text('explorer.voyage.reading', {name: n.name}), this.hudSteps.at(-1)?.startsWith(prefix));
      }
    }
    if (!this.loop && this.dist >= total) {
      if (this.mode === 'travel') {
        if (this.readExpected) this.startReading();
        else {
          this.mode = 'wait';
          this.modeAt = this.t;
        }
      } else if (this.mode === 'final') {
        this.mode = 'done';
        this.landedAt = this.t;
      }
    }
  }

  private radarDone(): void {
    const f = this.pendingFocus;
    const c = this.pendingCandidates;
    const stop = this.pendingEnd;
    this.pendingFocus = null;
    this.pendingCandidates = null;
    this.pendingEnd = false;
    if (f) {
      if (c) this.showCandidates(c);
      this.showFocus(...f);
    } else if (stop) {
      this.mode = 'idle';
      this.route = [];
    } else if (c) this.showCandidates(c);
    else this.patrol();
  }

  /** No candidate list yet: sweep the biggest clusters. */
  private patrol(): void {
    const stops = (this.galaxy?.clusters ?? []).slice(0, 9).map((g) => g.members[0]).filter(Boolean);
    this.setRoute([{xy: this.origin}, ...this.tour(this.origin, stops).map((n) => ({n}))], 260);
    this.mode = 'travel';
    this.modeAt = this.t;
    this.log(this.hooks.text('explorer.voyage.clusters'));
  }

  private startReading(): void {
    const byKey = this.galaxy?.byKey;
    const fin = this.candidateList
      .slice(0, this.shortlist || 8)
      .map((c) => byKey?.get(c.key))
      .filter((n): n is Star => n !== undefined);
    if (fin.length < 2) {
      this.mode = 'wait';
      this.modeAt = this.t;
      return;
    }
    const here = this.shipPos();
    this.setRoute([{xy: here}, ...this.tour(here, fin).map((n) => ({n}))], 170, true);
    this.mode = 'read';
    this.modeAt = this.t;
    this.reading = null;
    this.log(this.hooks.text('explorer.voyage.finalists', {count: fin.length}));
    this.log(this.hooks.text('explorer.voyage.modelReading'));
  }

  private showCandidates(list: ScoredTable[]): void {
    const byKey = this.galaxy?.byKey;
    if (!byKey) return;
    this.candidateList = list.filter((c) => byKey.has(c.key)).sort((a, b) => (b.score || 0) - (a.score || 0));
    const stops = this.candidateList.slice(0, 12).map((c) => byKey.get(c.key) as Star);
    if (!stops.length) return;
    this.setRoute([{xy: this.origin}, ...this.tour(this.origin, stops).map((n) => ({n}))], 250);
    this.mode = 'travel';
    this.modeAt = this.t;
    this.trail = [];
    this.log(this.hooks.text('explorer.voyage.candidates', {count: this.candidateList.length}));
    this.log(this.hooks.text('explorer.voyage.routeDrawn'));
  }

  private showFocus(list: ScoredTable[], query?: string): void {
    const byKey = this.galaxy?.byKey;
    this.focusList = list.filter((f) => f && f.key && byKey?.has(f.key));
    this.focusAt = this.t;
    if (!this.active || !this.focusList.length) {
      if (!this.focusList.length && this.mode !== 'idle') {
        this.mode = 'idle';
        this.route = [];
        this.hudSteps = [];
        this.hooks.onLog('');
      }
      return;
    }
    const readingPrefix = this.hooks.text('explorer.voyage.reading', {name: ''});
    if (this.hudSteps.at(-1)?.startsWith(readingPrefix)) this.hudSteps.pop();
    const last = this.hudSteps.at(-1);
    if (last === this.hooks.text('explorer.voyage.modelReading') || last === this.hooks.text('explorer.voyage.routeDrawn'))
      this.hudSteps.pop();
    if (!this.hudSteps.length && query) this.hudSteps.push(this.hooks.text('explorer.voyage.query', {query}));
    this.log(this.hooks.text('explorer.voyage.arrived', {count: this.focusList.length, name: this.focusList[0].name}));
    const from = this.mode === 'idle' ? this.searchOrigin() : this.shipPos();
    const stops = [...this.focusList].reverse().map((f) => ({n: byKey?.get(f.key) as Star}));
    this.trail = [];
    this.setRoute([{xy: from}, ...stops], 900);
    this.mode = 'final';
    this.modeAt = this.t;
  }

  // --------------------------------------------------------------- drawing

  private draw(): void {
    const {ctx, palette: c, width: W, height: H} = this;
    const t = this.t;
    ctx.clearRect(0, 0, W, H);
    const cx = W / 2;
    const cy = H / 2;
    const galaxy = this.galaxy;
    if (galaxy) {
      for (const d of galaxy.dust) {
        const a = 0.25 + 0.35 * Math.sin(t * 0.002 + d.tw);
        ctx.fillStyle = rgba(c.dust, a * (0.3 + d.z * 0.5));
        ctx.fillRect(cx + d.x * W * 0.6, cy + d.y * H * 0.6, 1, 1);
      }
    }
    if (!galaxy) return;
    const voyage = this.mode !== 'idle';
    const onRoute = new Set(this.route.map((p) => ('n' in p ? p.n : null)).filter(Boolean));
    const dim = voyage && this.mode !== 'done' ? 0.3 : this.focusList.length ? 0.45 : 1;

    ctx.lineWidth = 0.5;
    for (const n of galaxy.stars) {
      const [x, y] = this.screen(n);
      const [gx, gy] = this.screen({x: n.g.x, y: n.g.y, z: n.z});
      ctx.strokeStyle = hsla(n.hue, c.link, 0.05 * dim);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(gx, gy);
      ctx.stroke();
    }
    for (const n of galaxy.stars) {
      const [x, y] = this.screen(n);
      n.sx = x;
      n.sy = y;
      const tw = 0.65 + 0.35 * Math.sin(t * 0.0022 + n.tw);
      const r = n.size * (0.6 + n.z * 0.7);
      const kin = !this.selected || n.g === this.selected.g ? 1 : 0.4;
      const a = (0.35 + 0.55 * n.z) * tw * (onRoute.has(n) ? 1 : dim) * kin;
      ctx.fillStyle = `hsla(${n.hue},${c.starSaturation},${c.starLightness + n.z * c.starLightnessDepth}%,${a})`;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, TAU);
      ctx.fill();
    }
    if (this.mode === 'plan') this.drawPlanning();
    if (this.route.length > 1 && this.mode !== 'idle') this.drawRoute();
    this.drawFocus();
    if (this.selected) this.drawSelected();
    if (this.hover && this.hover !== this.selected) this.ring(this.hover.sx, this.hover.sy, 10, c.hoverRing, 1.2);
  }

  /** Constellation of its cluster and a turning reticle (still with reduced motion). */
  private drawSelected(): void {
    const {ctx, palette: c} = this;
    const n = this.selected as Star;
    const x = n.sx;
    const y = n.sy;
    const age = (this.t - this.selectedAt) / 1000;
    const grow = Math.min(1, age * 2.5);
    ctx.lineWidth = 0.8;
    for (const m of n.g.members) {
      if (m === n) continue;
      ctx.strokeStyle = hsla(n.hue, c.kinLine, 0.16 * grow);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + (m.sx - x) * grow, y + (m.sy - y) * grow);
      ctx.stroke();
      ctx.fillStyle = hsla(n.hue, c.kinDot, 0.8 * grow);
      ctx.beginPath();
      ctx.arc(m.sx, m.sy, 1.6, 0, TAU);
      ctx.fill();
    }
    this.glow(x, y, 40 * grow, hsla(n.hue, c.selectedGlow, 0.4));
    const r = 15 + 14 * (1 - grow);
    const spin = this.t * 0.0011;
    ctx.strokeStyle = hsla(n.hue, c.reticle, 0.95 * grow);
    ctx.lineWidth = 1.6;
    for (let k = 0; k < 4; k++) {
      const a0 = spin + (k * Math.PI) / 2 + 0.22;
      ctx.beginPath();
      ctx.arc(x, y, r, a0, a0 + Math.PI / 2 - 0.44);
      ctx.stroke();
    }
    ctx.strokeStyle = hsla(n.hue, c.reticle, 0.35 * grow);
    ctx.lineWidth = 1;
    for (let k = 0; k < 4; k++) {
      // crosshair ticks
      const a = (k * Math.PI) / 2;
      ctx.beginPath();
      ctx.moveTo(x + Math.cos(a) * (r + 5), y + Math.sin(a) * (r + 5));
      ctx.lineTo(x + Math.cos(a) * (r + 12), y + Math.sin(a) * (r + 12));
      ctx.stroke();
    }
    const p = (age * 0.45) % 1;
    this.ring(x, y, r + p * 46, hsla(n.hue, c.ping, 0.45 * (1 - p)), 1);
    ctx.fillStyle = rgba(c.white, 1);
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, TAU);
    ctx.fill();
    this.label(x + 8, y - 6, n.name, '', grow);
  }

  /** Radar pings out of the search field while the route is computed. */
  private drawPlanning(): void {
    const {ctx, palette: c, width: W, height: H} = this;
    const [ox, oy] = this.origin;
    const age = (this.t - this.modeAt) / 1000;
    for (let k = 0; k < 3; k++) {
      const p = (age * 0.45 + k / 3) % 1;
      this.ring(ox, oy, 10 + p * Math.max(W, H) * 0.45, rgba(c.cyan, 0.35 * (1 - p)), 1.2);
    }
    const sweep = age * RADAR_SPEED;
    const g = typeof ctx.createConicGradient === 'function' ? ctx.createConicGradient(sweep, ox, oy) : null;
    if (g) {
      g.addColorStop(0, rgba(c.cyan, 0.09));
      g.addColorStop(0.035, rgba(c.cyan, 0));
      g.addColorStop(1, rgba(c.cyan, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(ox, oy, Math.max(W, H), 0, TAU);
      ctx.fill();
    }
    this.drawShip(ox, oy, -Math.PI / 2, 1);
  }

  private drawRoute(): void {
    const {ctx, palette: c} = this;
    const t = this.t;
    const {pts, cum, total} = this.lengths();
    const reveal = Math.min(1, (t - this.routeAt) / (this.mode === 'final' ? 300 : 700));
    const planned = total * reveal;
    const d = this.along(cum, total);
    // planned path ahead (dashed, drawn out progressively)
    ctx.setLineDash([5, 9]);
    ctx.lineDashOffset = -t * 0.04;
    ctx.strokeStyle = this.mode === 'read' ? rgba(c.pink, 0.45) : rgba(c.cyan, 0.4);
    ctx.lineWidth = 1.2;
    this.polyline(pts, cum, this.loop ? 0 : d, planned);
    ctx.setLineDash([]);
    // travelled path (solid, glowing)
    if (!this.loop) {
      ctx.strokeStyle = rgba(c.cyan, 0.18);
      ctx.lineWidth = 6;
      this.polyline(pts, cum, 0, d);
      ctx.strokeStyle = rgba(c.trail, 0.9);
      ctx.lineWidth = 1.6;
      this.polyline(pts, cum, 0, d);
    }
    // waypoints
    this.route.forEach((p, k) => {
      if (k === 0 || !('n' in p)) return;
      const [x, y] = this.point(p);
      const scored =
        this.candidateList.find((s) => s.key === p.n.key) || this.focusList.find((f) => f.key === p.n.key);
      const since = this.arrived[k] ? (t - this.arrived[k]) / 1000 : -1;
      if (since >= 0 && since < 1.2) this.ring(x, y, 6 + since * 34, rgba(c.cyan, 0.8 * (1 - since / 1.2)), 1.5);
      this.ring(x, y, since >= 0 ? 6 : 4, since >= 0 ? rgba(c.white, 0.85) : rgba(c.cyan, 0.5), 1.2);
      const show = this.mode === 'read' ? p.n === this.reading : since >= 0 && since < 2.2 && this.mode !== 'final';
      if (show)
        this.label(
          x,
          y,
          this.mode === 'read' ? this.hooks.text('explorer.voyage.readingLabel', {name: p.n.name}) : p.n.name,
          scored && scored.score != null ? this.hooks.text('explorer.star.score', {score: Math.round(scored.score * 100)}) : '',
          1,
        );
    });
    if (this.mode === 'done') {
      const [x, y] = pts[pts.length - 1];
      const a = (t - this.landedAt) / 1000;
      if (a < 1.6)
        for (let k = 0; k < 3; k++)
          this.ring(x, y, 8 + (a + k * 0.18) * 70, rgba(c.mint, Math.max(0, 0.8 - a * 0.5 - k * 0.15)), 2);
      if (a > 4) this.route = [];
      return;
    }
    const [sx, sy, ang] = this.at(pts, cum, d);
    this.trail.push([sx, sy]);
    if (this.trail.length > 26) this.trail.shift();
    this.drawShip(sx, sy, ang, 1);
  }

  private polyline(pts: [number, number][], cum: number[], from: number, to: number): void {
    if (to <= from) return;
    const {ctx} = this;
    const [x0, y0] = this.at(pts, cum, from);
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    for (let i = 1; i < pts.length; i++) {
      if (cum[i] <= from) continue;
      if (cum[i] >= to) {
        const [x, y] = this.at(pts, cum, to);
        ctx.lineTo(x, y);
        break;
      }
      ctx.lineTo(pts[i][0], pts[i][1]);
    }
    ctx.stroke();
  }

  private drawShip(x: number, y: number, ang: number, alpha: number): void {
    const {ctx, palette: c, trail} = this;
    for (let i = 1; i < trail.length; i++) {
      // comet trail
      const k = i / trail.length;
      ctx.strokeStyle = rgba(c.cyan, 0.5 * k * alpha);
      ctx.lineWidth = 3.5 * k;
      ctx.beginPath();
      ctx.moveTo(trail[i - 1][0], trail[i - 1][1]);
      ctx.lineTo(trail[i][0], trail[i][1]);
      ctx.stroke();
    }
    this.glow(x, y, 26, rgba(c.cyan, 0.45 * alpha));
    this.glow(x, y, 12, rgba(c.pink, 0.35 * alpha));
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(ang);
    ctx.fillStyle = rgba(c.white, 1);
    ctx.beginPath();
    ctx.moveTo(9, 0);
    ctx.lineTo(-6, 5);
    ctx.lineTo(-3, 0);
    ctx.lineTo(-6, -5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  private glow(x: number, y: number, r: number, color: string): void {
    if (r <= 0) return;
    const {ctx} = this;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, color);
    g.addColorStop(1, 'transparent');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, TAU);
    ctx.fill();
  }

  private ring(x: number, y: number, r: number, color: string, w: number): void {
    const {ctx} = this;
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, TAU);
    ctx.stroke();
  }

  private drawFocus(): void {
    if (!this.focusList.length || (this.mode !== 'done' && this.mode !== 'idle')) return;
    const {ctx, palette: c} = this;
    const byKey = this.galaxy?.byKey;
    const t = this.t;
    const age = (t - this.focusAt) / 1000;
    const pts = this.focusList.map((f) => byKey?.get(f.key)).filter((n): n is Star => n !== undefined);
    if (pts.length > 1 && this.mode === 'idle') {
      ctx.setLineDash([6, 8]);
      ctx.lineDashOffset = -t * 0.03;
      ctx.strokeStyle = rgba(c.cyan, 0.45);
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(pts[0].sx, pts[0].sy);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].sx, pts[i].sy);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    this.focusList.forEach((f, i) => {
      const n = byKey?.get(f.key);
      if (!n) return;
      const appear = Math.max(0, Math.min(1, age * 2 - i * 0.15));
      if (!appear) return;
      const s = Math.max(0.15, f.score || 0);
      const pulse = 1 + 0.2 * Math.sin(t * 0.004 - i);
      this.glow(n.sx, n.sy, (16 + 26 * s) * pulse * appear, rgba(c.cyan, 0.32 * appear));
      this.ring(n.sx, n.sy, (7 + 9 * s) * pulse, rgba(c.white, 0.7 * appear), 1.3);
      ctx.fillStyle = i === 0 ? rgba(c.mint, 1) : rgba(c.white, 1);
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, 2.6 + 2 * s, 0, TAU);
      ctx.fill();
      if (i < 6)
        this.label(
          n.sx,
          n.sy,
          this.hooks.text('explorer.star.rank', {rank: i + 1, name: f.name}),
          f.score != null ? this.hooks.text('explorer.star.score', {score: Math.round(f.score * 100)}) : '',
          appear,
        );
    });
  }

  private label(x: number, y: number, text: string, score: string, alpha: number): void {
    const {ctx, palette: c} = this;
    ctx.font = c.labelFont;
    const w = ctx.measureText(text).width + (score ? 44 : 14);
    const lx = Math.max(8, Math.min(this.width - w - 8, x + 14));
    const ly = y - 24;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = c.labelBg;
    ctx.strokeStyle = rgba(c.cyan, 0.45);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(lx, ly, w, 20, 9);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = c.labelText;
    ctx.fillText(text, lx + 7, ly + 14);
    if (score) {
      ctx.fillStyle = rgba(c.mint, 1);
      ctx.fillText(score, lx + w - 37, ly + 14);
    }
    ctx.globalAlpha = 1;
  }

  // --------------------------------------------------------------- interaction

  private pointerMove(e: PointerEvent): void {
    this.mouse.x = e.clientX / innerWidth;
    this.mouse.y = e.clientY / innerHeight;
    if (!this.active || !this.galaxy) return;
    const target = e.target instanceof Element ? e.target : null;
    const n = target && !this.hooks.blocked(target) ? nearestStar(this.galaxy.stars, e.clientX, e.clientY) : null;
    this.hover = n;
    this.hooks.onHover(n, e.clientX, e.clientY);
  }

  private click(e: MouseEvent): void {
    if (!this.active || !this.galaxy) return;
    const target = e.target instanceof Element ? e.target : null;
    if (!target || !target.isConnected) return; // a re-rendered control inside the panel
    const n = !this.hooks.blocked(target) ? nearestStar(this.galaxy.stars, e.clientX, e.clientY) : null;
    if (n) this.hooks.onStarClick(n.key);
    else if (this.selected && !target.closest('.dossier')) this.hooks.onSkyClick();
  }
}
