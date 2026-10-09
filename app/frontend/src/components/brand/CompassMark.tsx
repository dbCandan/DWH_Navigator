import './brand.css';

/** The main screen's compass (index.html header.top); its needle turns while an analysis runs. */
export function CompassMark() {
  return (
    <svg className="compass" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
      <circle className="compass-disc" cx="16" cy="16" r="14" />
      <circle className="compass-rim" cx="16" cy="16" r="10.5" />
      <g className="needle">
        <path className="compass-north" d="M16 5l4 11-4 11-4-11z" />
        <path className="compass-south" d="M16 16l4 0-4 11-4-11z" />
      </g>
    </svg>
  );
}
