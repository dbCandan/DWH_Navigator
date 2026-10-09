import {createElement} from 'react';

type Shape = readonly [tag: 'path' | 'circle' | 'ellipse', attributes: Readonly<Record<string, string>>];

/** The admin screen's line icons (admin.html ICONS), 24-unit grid, drawn with currentColor. */
const ICONS = {
  home: [['path', {d: 'M3 11l9-7 9 7'}], ['path', {d: 'M5 10v10h14V10'}], ['path', {d: 'M10 20v-6h4v6'}]],
  chart: [['path', {d: 'M4 20V10M10 20V4M16 20v-7M22 20H2'}]],
  book: [['path', {d: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z'}], ['path', {d: 'M4 19V5M8 7h7M8 11h7'}]],
  spark: [['path', {d: 'M12 3l1.9 4.6 4.6 1.9-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z'}], ['path', {d: 'M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z'}]],
  sliders: [['path', {d: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0'}], ['circle', {cx: '16', cy: '6', r: '2'}], ['circle', {cx: '10', cy: '12', r: '2'}], ['circle', {cx: '18', cy: '18', r: '2'}]],
  wrench: [['path', {d: 'M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z'}]],
  search: [['circle', {cx: '11', cy: '11', r: '6.5'}], ['path', {d: 'M16 16l5 5'}]],
  import: [['path', {d: 'M12 3v12M7 10l5 5 5-5'}], ['path', {d: 'M4 15v5h16v-5'}]],
  export: [['path', {d: 'M12 15V3M7 8l5-5 5 5'}], ['path', {d: 'M4 15v5h16v-5'}]],
  file: [['path', {d: 'M6 3h9l4 4v14H6z'}], ['path', {d: 'M14 3v5h5'}]],
  refresh: [['path', {d: 'M20 11a8 8 0 1 0-2.3 5.7'}], ['path', {d: 'M20 4v7h-7'}]],
  plus: [['path', {d: 'M12 5v14M5 12h14'}]],
  bolt: [['path', {d: 'M13 2L4 14h7l-1 8 9-12h-7z'}]],
  db: [['ellipse', {cx: '12', cy: '6', rx: '7', ry: '3'}], ['path', {d: 'M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3'}]],
  layers: [['path', {d: 'M12 3l9 5-9 5-9-5z'}], ['path', {d: 'M3 13l9 5 9-5'}]],
  clock: [['circle', {cx: '12', cy: '12', r: '8.5'}], ['path', {d: 'M12 7.5V12l3 2'}]],
  arrow: [['path', {d: 'M5 12h14M13 6l6 6-6 6'}]],
  x: [['path', {d: 'M6 6l12 12M18 6L6 18'}]],
  list: [['path', {d: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01'}]],
  gauge: [['path', {d: 'M4 18a9 9 0 1 1 16 0'}], ['path', {d: 'M12 13l4-4'}]],
  // The super admin's Kullanıcılar page, in the same line style (user-accounts Requirement 16).
  users: [['circle', {cx: '9', cy: '8', r: '3.5'}], ['path', {d: 'M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6'}], ['path', {d: 'M16 4.6a3.5 3.5 0 0 1 0 6.8M21 20c0-2.6-1.6-4.8-4-5.6'}]],
} satisfies Record<string, readonly Shape[]>;

export type IconName = keyof typeof ICONS;

export function Icon({name}: {name: IconName}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {(ICONS[name] as readonly Shape[]).map(([tag, attributes], index) => createElement(tag, {key: index, ...attributes}))}
    </svg>
  );
}
