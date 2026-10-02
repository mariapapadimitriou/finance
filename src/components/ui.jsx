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
  const width = max > 0 ? Math.max((value / max) * 100, 1) : 0;
  return (
    <div className="bar-row">
      <div>
        <div className="name" title={name}>{name}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <div className="track">
        <div className={`fill${alt ? ' alt' : ''}`} style={{ width: `${width}%` }} />
      </div>
      <div className="val num">{formatted ?? money(value)}</div>
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
      <span aria-hidden="true">{icon}</span>
      {children}
    </span>
  );
}

export function Notice({ kind = '', children }) {
  return <div className={`notice ${kind}`}>{children}</div>;
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
    <Notice kind="error">
      {String(error.message || error)}
      {onRetry && (
        <>
          {' '}
          <button className="btn quiet" onClick={onRetry}>Retry</button>
        </>
      )}
    </Notice>
  );
}

/**
 * One voice for "the data behind this month may be incomplete".
 *
 * Overview and Budgets both face exactly this situation and each had its own
 * wording for it — "the data stops at day 27" on one tab, "the data stops short
 * of its last day" on the other — so one fact read as two different problems
 * depending on where you happened to be standing. The distinction that does
 * matter is kept: a month still running will fill up by itself, and a finished
 * month the data stops short of will not.
 *
 * `month` is the month being shown, `summary` the payload from /api/summary.
 */
export function MonthFreshness({ month, summary, onTab }) {
  const shown = month === summary?.latest_month;
  if (!shown || summary?.latest_month_complete) return null;

  const lastDay = summary?.date_range?.[1]?.slice(8);
  const running = summary?.latest_month_running;
  const label = monthName(month);

  return (
    <Notice>
      {running ? (
        <>
          {label} is still in progress
          {lastDay && <> — your data runs to day {Number(lastDay)}</>}. Anything
          compared against whole months will read low until it closes.
        </>
      ) : (
        <>
          <strong>
            {label} is over, but the data{' '}
            {lastDay ? <>stops at day {Number(lastDay)}</> : <>stops short of its last day</>}.
          </strong>{' '}
          That is either a quiet end to the month or a sync that hasn&apos;t run
          since — they look identical from here.{' '}
          {onTab
            ? <>Sync on the{' '}
                <button className="link" onClick={() => onTab('banks')}>
                  Banks tab
                </button>{' '}before reading anything into this month.</>
            : <>Sync on the Banks tab before reading anything into this month.</>}
        </>
      )}
    </Notice>
  );
}

function monthName(month) {
  if (!month) return 'This month';
  const d = new Date(`${month}-01T00:00:00`);
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}
