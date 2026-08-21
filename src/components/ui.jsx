// Small shared presentation pieces.

import { money } from '../api.js';

export function Card({ title, hint, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {hint && <div className="hint">{hint}</div>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

/** A single number that is the whole story — no chart needed. */
export function Tile({ label, value, note, delta }) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {delta !== undefined && delta !== null && (
        <div className="note">
          <span className={`delta ${delta > 0 ? 'up' : 'down'}`}>
            {delta > 0 ? '↑' : '↓'} {money(Math.abs(delta))}
          </span>{' '}
          {note}
        </div>
      )}
      {delta === undefined && note && <div className="note">{note}</div>}
    </div>
  );
}

/**
 * One horizontal bar with a direct label.
 *
 * Built in HTML rather than on a canvas so the value always sits beside the
 * bar at full contrast, never clipped inside a short one.
 */
export function BarRow({ name, sub, value, max, formatted, alt = false }) {
  const width = max > 0 ? Math.max((value / max) * 100, 0.6) : 0;
  return (
    <div className="bar-row">
      <div>
        <div className="name" title={name}>{name}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <div className="track">
        <div className={`fill${alt ? ' alt' : ''}`} style={{ width: `${width}%` }} />
      </div>
      <div className="val">{formatted ?? money(value)}</div>
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend">
      {items.map((it) => (
        <span className="item" key={it.label}>
          <span className="swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Status is never carried by colour alone — every state ships an icon and a word. */
export function StatusPill({ state, children }) {
  const icon = { good: '✓', warning: '!', critical: '✕' }[state] ?? '•';
  return (
    <span className={`pill ${state}`}>
      <span className="status-dot" aria-hidden="true" />
      <span aria-hidden="true">{icon}</span>
      {children}
    </span>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}

export function Loading({ what = 'data' }) {
  return <div className="empty muted">Loading {what}…</div>;
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="notice error">
      {String(error.message || error)}
      {onRetry && (
        <>
          {' '}
          <button className="btn quiet" onClick={onRetry}>Retry</button>
        </>
      )}
    </div>
  );
}
