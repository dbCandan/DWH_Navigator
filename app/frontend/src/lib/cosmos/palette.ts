/**
 * The canvas map's colors and label font, read from the design tokens in globals.css
 * (dictionary-explorer Requirement 17): the drawing code holds no color of its own. RGB triplets
 * get their opacity while drawing; tone pairs are a cluster hue's saturation and lightness.
 */
export interface CosmosPalette {
  dust: string;
  cyan: string;
  pink: string;
  mint: string;
  white: string;
  trail: string;
  hoverRing: string;
  labelBg: string;
  labelText: string;
  labelFont: string;
  link: string;
  starSaturation: string;
  starLightness: number;
  starLightnessDepth: number;
  kinLine: string;
  kinDot: string;
  selectedGlow: string;
  reticle: string;
  ping: string;
}

export function readCosmosPalette(element: Element = document.documentElement): CosmosPalette {
  const style = getComputedStyle(element);
  const token = (name: string) => style.getPropertyValue(`--cosmos-${name}`).trim();
  return {
    dust: token('dust'),
    cyan: token('cyan'),
    pink: token('pink'),
    mint: token('mint'),
    white: token('white'),
    trail: token('trail'),
    hoverRing: token('hover-ring'),
    labelBg: token('label-bg'),
    labelText: token('label-text'),
    labelFont: token('label-font'),
    link: token('link'),
    starSaturation: token('star-saturation'),
    starLightness: Number(token('star-lightness')),
    starLightnessDepth: Number(token('star-lightness-depth')),
    kinLine: token('kin-line'),
    kinDot: token('kin-dot'),
    selectedGlow: token('selected-glow'),
    reticle: token('reticle'),
    ping: token('ping'),
  };
}

/** `rgba(<triplet>, alpha)` for a token triplet. */
export const rgba = (triplet: string, alpha: number) => `rgba(${triplet},${alpha})`;

/** `hsla(hue, <saturation, lightness>, alpha)` for a token pair. */
export const hsla = (hue: number, tone: string, alpha: number) => `hsla(${hue},${tone},${alpha})`;
