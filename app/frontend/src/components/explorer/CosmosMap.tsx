import {useEffect, useRef, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useRootClass} from '@/hooks/useSurface';
import {CosmosEngine, type CosmosHooks} from '@/lib/cosmos/engine';
import type {GalaxyItem, Star} from '@/lib/cosmos/layout';
import {readCosmosPalette} from '@/lib/cosmos/palette';

/** Counts in Turkish grouping: 12.109. */
const fmt = (n: number) => n.toLocaleString('tr-TR');

/** Pointer targets that keep the stars from being picked (dictionary-explorer Requirement 6). */
const BLOCKING = 'header, .answer, .searchbox, button, a, textarea, input, table, details, footer, .dossier';

interface Props {
  galaxy: readonly GalaxyItem[] | null;
  /** The engine, once drawing; null after unmount. */
  onEngine?: (engine: CosmosEngine | null) => void;
  onStarClick?: (key: string) => void;
  onSkyClick?: () => void;
}

interface Tip {
  star: Star;
  x: number;
  y: number;
}

/**
 * The map behind the page: the canvas (hidden from screen readers), the HUD in the lower left
 * and the star tooltip (Requirement 5 and 6). Loaded lazily; the shell and the question bar
 * work without it.
 */
export default function CosmosMap({galaxy, onEngine, onStarClick, onSkyClick}: Props) {
  const {t} = useIntl();
  const canvas = useRef<HTMLCanvasElement>(null);
  const engine = useRef<CosmosEngine | null>(null);
  const [count, setCount] = useState('');
  const [log, setLog] = useState('');
  const [tip, setTip] = useState<Tip | null>(null);
  // Callbacks change between renders; the engine reads the latest through a ref.
  const latest = useRef({t, onStarClick, onSkyClick});
  useEffect(() => {
    latest.current = {t, onStarClick, onSkyClick};
  });
  useRootClass('star-hover', tip !== null);

  useEffect(() => {
    const element = canvas.current;
    if (element === null) return;
    const hooks: CosmosHooks = {
      onCount: (tables, clusters, columns) =>
        setCount(latest.current.t('explorer.hud.count', {clusters: fmt(clusters), tables: fmt(tables), columns: fmt(columns)})),
      onLog: setLog,
      onHover: (star, x, y) => setTip(star ? {star, x, y} : null),
      onStarClick: (key) => {
        setTip(null);
        latest.current.onStarClick?.(key);
      },
      onSkyClick: () => latest.current.onSkyClick?.(),
      searchOrigin: () => {
        const box = document.querySelector('.searchbox')?.getBoundingClientRect();
        return box && box.width ? [box.left + box.width / 2, Math.min(innerHeight - 40, box.bottom + 8)] : null;
      },
      panelWidth: () => document.getElementById('dossier')?.offsetWidth ?? 0,
      blocked: (target) => document.documentElement.classList.contains('has-results') || target.closest(BLOCKING) !== null,
      text: (key, values) => latest.current.t(key, values),
    };
    let created: CosmosEngine;
    try {
      created = new CosmosEngine(element, readCosmosPalette(), hooks);
    } catch {
      return; // no 2D canvas: the page works without the map (Requirement 5)
    }
    engine.current = created;
    created.start();
    onEngine?.(created);
    return () => {
      onEngine?.(null);
      created.destroy();
      engine.current = null;
    };
  }, [onEngine]);

  useEffect(() => {
    // Without data the page still works; the map stays empty (Requirement 5).
    if (galaxy !== null) engine.current?.load(galaxy);
  }, [galaxy]);

  return (
    <>
      <canvas id="cosmos" ref={canvas} aria-hidden="true" />
      <div id="hud" aria-hidden="true">
        <div>
          <b>{t('explorer.hud.universe')}</b> · <span id="hud-count">{count}</span>
        </div>
        <div className="focus" id="hud-focus">
          {log}
        </div>
      </div>
      <div
        id="star-tip"
        role="tooltip"
        className={tip ? 'on' : undefined}
        style={tip ? {left: tip.x + 'px', top: tip.y + 'px'} : undefined}
      >
        {tip && (
          <>
            <div className="t">{tip.star.name}</div>
            <div className="g">{t('explorer.star.columns', {schema: tip.star.schema, columns: tip.star.columns})}</div>
            <div className="g">{tip.star.group}</div>
          </>
        )}
      </div>
    </>
  );
}
