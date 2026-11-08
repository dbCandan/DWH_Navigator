import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {CosmosEngine, MERGE_MS, RADAR_MS, type CosmosHooks} from './engine';
import type {GalaxyItem} from './layout';
import type {CosmosPalette} from './palette';

const palette: CosmosPalette = {
  dust: '1, 2, 3', cyan: '1, 2, 3', pink: '1, 2, 3', mint: '1, 2, 3', amber: '1, 2, 3', white: '1, 2, 3', trail: '1, 2, 3',
  hoverRing: 'token', labelBg: 'token', labelText: 'token', labelFont: '12px monospace', link: '1%, 2%',
  starSaturation: '1%', starLightness: 70, starLightnessDepth: 10, kinLine: '1%, 2%', kinDot: '1%, 2%',
  selectedGlow: '1%, 2%', reticle: '1%, 2%', ping: '1%, 2%',
};

const ITEMS: GalaxyItem[] = ['A', 'B', 'C', 'D'].map((name, i) => ({
  key: `DWH.Ornek.v${name}`,
  name: `v${name}`,
  schema: 'DWH.Ornek',
  group: i < 2 ? 'Müşteri' : 'Kredi',
  columns: 10 + i,
}));

/** A 2D context that records nothing: drawing is not tested pixel by pixel (rules/14). */
function fakeCanvas(): HTMLCanvasElement {
  const ctx = new Proxy({} as Record<string, unknown>, {
    get: (target, name) => {
      if (name in target) return target[name as string];
      if (name === 'measureText') return () => ({width: 40});
      if (name === 'createRadialGradient' || name === 'createConicGradient') return () => ({addColorStop: () => undefined});
      return () => undefined;
    },
    set: (target, name, value) => {
      target[name as string] = value;
      return true;
    },
  });
  const canvas = document.createElement('canvas');
  vi.spyOn(canvas, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  return canvas;
}

function hooks(log: string[]): CosmosHooks {
  return {
    onCount: () => undefined,
    onLog: (text) => log.push(text),
    onHover: () => undefined,
    onStarClick: () => undefined,
    onSkyClick: () => undefined,
    searchOrigin: () => [100, 100],
    panelWidth: () => 0,
    blocked: () => false,
    text: (key, values) => `${key}${values ? ' ' + JSON.stringify(values) : ''}`,
  };
}

describe('map drawing loop (dictionary-explorer Requirement 5 and 8)', () => {
  let frames: FrameRequestCallback[];
  beforeEach(() => {
    frames = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  const runFrames = (count: number, step = 40) => {
    for (let i = 0; i < count && frames.length; i++) frames.shift()?.(performance.now() + (i + 1) * step);
  };

  it('keeps drawing while motion is allowed', () => {
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks([]));
    engine.start();
    engine.load(ITEMS);
    runFrames(5);
    expect(frames.length).toBe(1); // every frame asks for the next one
    expect(engine.radarMs).toBe(RADAR_MS);
    engine.destroy();
  });

  it('lands the answer only after the radar\'s turn; the loop goes on (Requirement 7, 8)', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log));
    engine.start();
    engine.load(ITEMS);
    engine.begin();
    expect(log.at(-1)).toBe(''); // no "kolon taranıyor" line: the log waits for the radar's finds
    engine.focus([{key: 'DWH.Ornek.vA', name: 'vA', score: 0.9}], 'soru');
    expect(log.at(-1)).not.toContain('explorer.voyage.arrived'); // the radar is still turning
    runFrames(Math.ceil(RADAR_MS / 40) + 5);
    expect(log.at(-1)).toContain('explorer.voyage.arrived');
    expect(frames.length).toBe(1);
    engine.destroy();
  });

  it('lands a saved answer at once: the radar does not turn', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log));
    engine.start();
    engine.load(ITEMS);
    engine.begin();
    engine.skipRadar();
    engine.focus([{key: 'DWH.Ornek.vA', name: 'vA', score: 0.9}], 'soru');
    runFrames(5);
    expect(log.at(-1)).toContain('explorer.voyage.arrived');
    engine.destroy();
  });

  it('marks found tables on the radar, merges them and reads only the final ones (question-analysis)', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log));
    engine.start();
    engine.load(ITEMS);
    engine.begin();
    engine.found('prefilter', [
      {key: 'DWH.Ornek.vA', source: 'engine'},
      {key: 'DWH.Ornek.vC', source: 'engine'},
      {key: 'DWH.Ornek.yok', source: 'engine'}, // not on the map: skipped
    ]);
    expect(log.at(-1)).toContain('explorer.voyage.found {"count":2}');
    engine.found('reading', [
      {key: 'DWH.Ornek.vA', source: 'model', read: true},
      {key: 'DWH.Ornek.vB', source: 'family', read: true},
      {key: 'DWH.Ornek.vD', source: 'similar', read: false},
    ]);
    // one line, its count kept current: no second "found" line
    expect(log.at(-1)).toContain('explorer.voyage.found {"count":4}');
    expect(log.at(-1)).not.toContain('explorer.voyage.found {"count":2}');
    // one radar turn (the beam passes every mark), the marks' moment in sight, then the merge
    runFrames(Math.ceil((RADAR_MS + 2500 + MERGE_MS) / 40) + 10);
    expect(log.some((l) => l.includes('explorer.voyage.finalists {"count":2}'))).toBe(true);
    expect(log.some((l) => l.includes('explorer.voyage.reading'))).toBe(true);
    engine.focus([{key: 'DWH.Ornek.vB', name: 'vB', score: 0.8}], 'soru');
    expect(log.at(-1)).toContain('explorer.voyage.arrived');
    engine.destroy();
  });

  it('keeps the radar turning while step 1 found nothing to read', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log));
    engine.start();
    engine.load(ITEMS);
    engine.begin();
    engine.found('reading', []);
    runFrames(Math.ceil((RADAR_MS + MERGE_MS) / 40) + 40);
    expect(log.some((l) => l.includes('explorer.voyage.finalists'))).toBe(false);
    engine.end();
    engine.destroy();
  });

  it('finds a table by its typed name only once the map has data', () => {
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks([]));
    expect(engine.find('vA')).toBeNull();
    engine.load(ITEMS);
    expect(engine.find('va')?.key).toBe('DWH.Ornek.vA');
    expect(engine.select('DWH.Ornek.vB')?.name).toBe('vB');
    engine.destroy();
  });
});
