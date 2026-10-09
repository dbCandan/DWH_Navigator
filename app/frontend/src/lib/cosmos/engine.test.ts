import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {CosmosEngine, RADAR_MS, type CosmosHooks} from './engine';
import type {GalaxyItem} from './layout';
import type {CosmosPalette} from './palette';

const palette: CosmosPalette = {
  dust: '1, 2, 3', cyan: '1, 2, 3', pink: '1, 2, 3', mint: '1, 2, 3', white: '1, 2, 3', trail: '1, 2, 3',
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
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks([]), false);
    engine.start();
    engine.load(ITEMS);
    runFrames(5);
    expect(frames.length).toBe(1); // every frame asks for the next one
    expect(engine.radarMs).toBe(RADAR_MS);
    engine.destroy();
  });

  it('draws once per change and never loops with reduced motion; the radar is not waited for', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log), true);
    engine.start();
    engine.load(ITEMS);
    runFrames(10);
    expect(frames.length).toBe(0);
    expect(engine.radarMs).toBe(0);

    engine.begin({columns: 1200});
    expect(log.at(-1)).toContain('explorer.voyage.scanningColumns');
    engine.focus([{key: 'DWH.Ornek.vA', name: 'vA', score: 0.9}], 'soru');
    expect(log.at(-1)).toContain('explorer.voyage.arrived');
    expect(frames.length).toBe(1); // one still frame for the constellation
    runFrames(1);
    expect(frames.length).toBe(0);
    engine.destroy();
  });

  it('writes "sırada" once in the voyage log while the analysis waits, without a count', () => {
    const log: string[] = [];
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks(log), true);
    engine.start();
    engine.load(ITEMS);
    engine.begin({columns: 1200});
    engine.queued();
    engine.queued();
    expect(log.at(-1)).toBe('explorer.voyage.scanningColumns {"columns":"1.200"}explorer.voyage.separatorexplorer.voyage.queued');
    engine.destroy();
  });

  it('finds a table by its typed name only once the map has data', () => {
    const engine = new CosmosEngine(fakeCanvas(), palette, hooks([]), true);
    expect(engine.find('vA')).toBeNull();
    engine.load(ITEMS);
    expect(engine.find('va')?.key).toBe('DWH.Ornek.vA');
    expect(engine.select('DWH.Ornek.vB')?.name).toBe('vB');
    engine.destroy();
  });
});
