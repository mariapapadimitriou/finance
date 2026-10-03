// Small shared presentation pieces.

import { useState } from 'react';
import { money } from '../api.js';
import { destination } from '../nav.js';

/**
 * A link to somewhere else in the app, named the way the app names it now.
 *
 * Panels used to write the destination into their own sentences — "sync on
 * the Banks tab" — and went on saying it long after Banks became Connections
 * inside Settings. The text comes from `nav.js` instead: the section name
 * when you are already in its group, "Settings → Connections" when you are
 * not. `from` is the panel the sentence is on.
 */
export function GoTo({ to, from, onTab, children }) {
  const text = children ?? destination(to, from);
  if (!onTab) return <strong>{text}</strong>;
  return (
    <button className="link" onClick={() => onTab(to)}>{text}</button>
  );
}

/**
 * An explanation you can put away.
 *
 * Nearly every card ends in a paragraph saying why its figure is what it is.
 * Worth reading once; noise on the fiftieth visit. So each opens the first
 * time and, once collapsed, stays collapsed — remembered per explanation in
 * this browser. Storage can be missing or refuse (a private window), and
 * then it simply stays open, which is where it started.
 */
export function Why({ id, label = 'Why?', children }) {
  const key = `spendie.why.${id}`;
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(key) !== 'closed'; } catch { return true; }
  });

  function onToggle(e) {
    const next = e.currentTarget.open;
    if (next === open) return;
    setOpen(next);
    try {
      if (next) localStorage.removeItem(key);
      else localStorage.setItem(key, 'closed');
    } catch { /* stays as it is for this visit */ }
  }

  return (
    <details className="why" open={open} onToggle={onToggle}>
      <summary>{label}</summary>
      <div className="assumption">{children}</div>
    </details>
  );
}

/**
 * Several notices as one strip: the most serious in full, the rest folded.
 *
 * Budgets could open with five notices before its first line — each true,
 * together pushing the table off the first screen and teaching you to skip
 * anything yellow. Callers pass them most serious first; only the first is
 * open, and every other is one bold line that expands where it stands.
 * Each item is `{ key, kind, summary, detail }`; null items are skipped.
 */
export function NoticeStack({ items }) {
  const shown = (items ?? []).filter(Boolean);
  if (shown.length === 0) return null;
  const [first, ...rest] = shown;
  return (
    <div className="notice-stack">
      <Notice kind={first.kind}>
        <strong>{first.summary}</strong>{first.detail && <> {first.detail}</>}
      </Notice>
      {rest.map((it) => (
        <details key={it.key} className={`notice folded ${it.kind ?? ''}`}>
          <summary><strong>{it.summary}</strong></summary>
          {it.detail && <div className="folded-body">{it.detail}</div>}
        </details>
      ))}
    </div>
  );
}

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
export function freshness(month, summary, { onTab, from } = {}) {
  const shown = month === summary?.latest_month;
  if (!shown || summary?.latest_month_complete) return null;

  const lastDay = summary?.date_range?.[1]?.slice(8);
  const running = summary?.latest_month_running;
  const label = monthName(month);

  if (running) {
    // A month still running fills itself in; it is information, not a
    // warning, so it is not set in bold on its own.
    return {
      key: 'freshness',
      kind: '',
      emphasis: false,
      summary: <>{label} is still in progress
        {lastDay && <> — your data runs to day {Number(lastDay)}</>}.</>,
      detail: <>Anything compared against whole months will read low until
        it closes.</>,
    };
  }
  return {
    key: 'freshness',
    kind: '',
    emphasis: true,
    summary: <>{label} is over, but the data{' '}
      {lastDay ? <>stops at day {Number(lastDay)}</> : <>stops short of its last day</>}.</>,
    detail: <>That is either a quiet end to the month or a sync that
      hasn&apos;t run since — they look identical from here. Sync in{' '}
      <GoTo to="banks" from={from} onTab={onTab} /> before reading anything
      into this month.</>,
  };
}

/** The same notice on its own, for a page with nothing else to stack it with. */
export function MonthFreshness({ month, summary, onTab, from }) {
  const it = freshness(month, summary, { onTab, from });
  if (!it) return null;
  return (
    <Notice kind={it.kind}>
      {it.emphasis ? <strong>{it.summary}</strong> : it.summary} {it.detail}
    </Notice>
  );
}

function monthName(month) {
  if (!month) return 'This month';
  const d = new Date(`${month}-01T00:00:00`);
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}
