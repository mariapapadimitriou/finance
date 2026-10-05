/**
 * Rings: a donut of parts, or one part of a whole on a grey track.
 *
 * Drawn in SVG rather than on a canvas so the colours are CSS variables and
 * follow the theme without being rebuilt. Each arc is a circle stroke cut to
 * length with a dash; the circle is turned so the first arc starts at the top
 * and they run clockwise.
 */

const GAP = 2.5; // px of track between neighbouring arcs

export function Donut({
  segments, total, size = 172, thickness = 16, marker, label, children,
  className = '',
}) {
  const parts = segments.filter((s) => s.value > 0);
  const sum = parts.reduce((t, s) => t + s.value, 0);
  const whole = Math.max(total ?? sum, sum, 0.000001);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  // One arc alone gets round ends, like a progress ring; several are cut
  // square so the gaps between them read as edges, not as more rounding.
  const round = parts.length === 1;
  const gap = parts.length > 1 ? GAP : 0;

  let start = 0;
  const arcs = parts.map((s) => {
    const share = Math.min(s.value / whole, 1);
    const span = share * c;
    // Round caps poke half a thickness past each end, so draw it shorter.
    let len = span - gap - (round && share < 1 ? thickness : 0);
    len = Math.max(len, round ? 0.01 : 0.5);
    const arc = { ...s, len, offset: start + (round && share < 1 ? thickness / 2 : 0) };
    start += span;
    return arc;
  });

  const tick = marker != null && marker >= 0 && marker <= 1
    ? marker * 2 * Math.PI - Math.PI / 2 : null;
  const mid = size / 2;

  return (
    <div className={`ring ${className}`.trim()} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}
           role="img" aria-label={label ?? arcs.map((a) => `${a.label} ${a.title ?? ''}`).join(', ')}>
        <circle cx={mid} cy={mid} r={r} fill="none"
                stroke="var(--ring-track)" strokeWidth={thickness} />
        <g transform={`rotate(-90 ${mid} ${mid})`}>
          {arcs.map((a) => (
            <circle key={a.label} className="arc" cx={mid} cy={mid} r={r} fill="none"
                    stroke={a.color} strokeWidth={thickness}
                    strokeLinecap={round ? 'round' : 'butt'}
                    strokeDasharray={`${a.len} ${c}`}
                    strokeDashoffset={-a.offset}>
              {a.title && <title>{`${a.label}: ${a.title}`}</title>}
            </circle>
          ))}
        </g>
        {tick != null && (
          <line x1={mid + (r - thickness / 2 - 3) * Math.cos(tick)}
                y1={mid + (r - thickness / 2 - 3) * Math.sin(tick)}
                x2={mid + (r + thickness / 2 + 3) * Math.cos(tick)}
                y2={mid + (r + thickness / 2 + 3) * Math.sin(tick)}
                stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" />
        )}
      </svg>
      {children && <div className="ring-center">{children}</div>}
    </div>
  );
}

/** The list beside a ring: a mark, a name, and its figure underneath. */
export function RingLegend({ items }) {
  return (
    <ul className="ring-legend">
      {items.filter(Boolean).map((it) => (
        <li key={it.label}>
          <span className={`mark${it.icon ? ' icon' : ''}${it.hollow ? ' hollow' : ''}`}
                style={it.icon ? { color: it.color ?? 'var(--ink-2)' }
                  : { background: it.hollow ? 'transparent' : it.color,
                      borderColor: it.color }}
                aria-hidden="true">
            {it.icon && <Icon name={it.icon} />}
          </span>
          <span>
            <span className="k">{it.label}</span>
            <span className={`v num${it.tone ? ` ${it.tone}` : ''}`}>{it.value}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

const ICONS = {
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  plus: 'M12 5v14M5 12h14',
  bag: 'M6 8h12l-1 12H7L6 8zM9 8a3 3 0 0 1 6 0',
  calendar: 'M4 6h16v14H4zM4 10h16M9 3v4M15 3v4',
  target: 'M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8z',
  trend: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  tick: 'M12 3v18M7 8l5-5 5 5',
};

function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
         strokeLinecap="round" strokeLinejoin="round">
      <path d={ICONS[name]} />
    </svg>
  );
}

/** A ring with its legend beside it — the shape every ring on the app takes. */
export function RingRow({ children }) {
  return <div className="ring-row">{children}</div>;
}
