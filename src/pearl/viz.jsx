import './viz.css';
import {
  breakdownRows, breakdownWords, deltaWords, dollars, fillPercent, fillWidth, paceFraction,
  paceNote, paceStatus, percentWords, progressLabel, rangeCells, sliderKey, sliderPercent,
  snapshotFill, THIN_DAYS,
} from './vizMath.js';

// The data visualisation patterns (THL-110, Pearl Design System V-01 to V-05).
// Every picture sits next to the numbers or words that say the same thing, so
// nothing rests on colour alone; there is no red, and never a single precise
// date. One fill colour (--action) for everything but the Anchor hero, which
// keeps the nacre. The arithmetic lives in vizMath.js.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthShort = (ym) => MONTHS[Number(ym.slice(5, 7)) - 1];

function Fill({ percent, className }) {
  const width = fillWidth(percent);
  return width ? <span className={className} style={{ width }} /> : null;
}

/**
 * V-01 Progress bar. `share` is 0–1; the fill is the exact percentage, at
 * least 4px above 0 and nothing at 0. Brand on the way, positive once done.
 * `name` says whose bar it is when the label alone doesn't. Without
 * `showLabel` the label row isn't drawn, though the bar still says it.
 */
export function ProgressBar({ label, value, share, tone = 'brand', name, showLabel = true }) {
  const pct = fillPercent(share);
  return (
    <div className="viz-progress">
      {showLabel && (
        <div className="viz-labels text-label" aria-hidden="true">
          <span className="viz-muted">{label}</span>
          <span>{value}</span>
        </div>
      )}
      <div className="viz-track" role="progressbar"
           aria-label={progressLabel(name ? `${name}, ${label}` : label, value, pct)}
           aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentWords(pct)}>
        <Fill percent={pct} className={`viz-fill${tone === 'positive' ? ' positive' : ''}`} />
      </div>
    </div>
  );
}

/**
 * V-01 PearlProgress, for the Anchor hero only: the nacre fill and a pearl
 * that grows from 16px to 40px with progress.
 */
export function PearlProgress({ title, saved, target, share, delta }) {
  const pct = fillPercent(share);
  const d = deltaWords(delta);
  const value = `${dollars(saved)} of ${dollars(target)}`;
  return (
    <div className="viz-pearl-progress">
      <span className="viz-pearl-slot" aria-hidden="true">
        <span className="viz-pearl" style={{ '--viz-share': pct / 100 }} />
      </span>
      <div className="viz-pearl-text">
        <div className="viz-labels">
          <span className="viz-pearl-title display-heading-3">{title}</span>
          <span className={`text-label viz-delta ${d.tone}`}>{d.text}</span>
        </div>
        <div className="viz-track" role="progressbar" aria-label={progressLabel(title, value, pct)}
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentWords(pct)}>
          <Fill percent={pct} className="viz-fill nacre" />
        </div>
        <p className="text-label viz-muted">{value} · {percentWords(pct)}% there</p>
      </div>
    </div>
  );
}

/**
 * V-02 Range band: ten months from this one, with the likely range filled.
 * Decorative: the headline beside it carries the answer. With no range there
 * is no date anywhere, so the axis goes too.
 */
export function RangeBand({ now, from, to }) {
  const cells = rangeCells(now, from, to);
  const any = cells.some((c) => c.state !== 'out');
  return (
    <div className="viz-range" aria-hidden="true">
      <div className="viz-range-track">
        {cells.map((c) => <span key={c.month} className={`viz-range-cell ${c.state}`} />)}
      </div>
      {any && (
        <div className="viz-range-axis text-label">
          {cells.map((c) => <span key={c.month}>{monthShort(c.month)}</span>)}
        </div>
      )}
    </div>
  );
}

/**
 * V-03 Snapshot bar: this month against a usual month. The fill is spent ÷
 * usual, capped; the tick is where she usually is by today. Over pace, or
 * over the month, turns champagne with a gold outline and says so in words.
 *
 * Rows measured against a plan rather than a usual month (Home's Income and
 * Savings, H-01) pass `share` (0–1) with their own `value` and `note`; they
 * have no tick and no pace. `share` null draws no bar at all, for a row with
 * nothing yet to measure against (E10: never an empty chart); `over` draws
 * it in champagne.
 *
 * Budget rows (THL-168 B-01) use the pace mode against the budget, with
 * their own `value` ("$412 of $460") and `note`, a string or a function of
 * the pace status, so the ±10% rule and the champagne stay the snapshot's.
 */
export function SnapshotBar({
  category, spent, usualMonth, usualByToday, day, daysInMonth, monthsOfHistory = 0,
  showTick = true, share, value, note, over: overShare = false,
}) {
  if (share !== undefined) {
    return (
      <div className="viz-snapshot">
        <div className="viz-labels text-body">
          <span>{category}</span>
          <span>{value}</span>
        </div>
        {share !== null && (
          <div className="viz-track tall" aria-hidden="true">
            <Fill percent={Math.min(Math.max(share || 0, 0), 1) * 100}
                  className={`viz-fill${overShare ? ' over' : ''}`} />
          </div>
        )}
        {note && <p className="text-label viz-muted">{note}</p>}
      </div>
    );
  }
  const fraction = paceFraction({ usualByToday, usualMonth, day, daysInMonth, monthsOfHistory });
  const status = paceStatus(spent, fraction * usualMonth, usualMonth);
  const over = status === 'over' || status === 'over-month';
  return (
    <div className="viz-snapshot">
      <div className="viz-labels text-body">
        <span>{category}</span>
        <span>{value ?? `${dollars(spent)} of a usual ${dollars(usualMonth)}`}</span>
      </div>
      <div className="viz-track tall" aria-hidden="true">
        <Fill percent={snapshotFill(spent, usualMonth) * 100}
              className={`viz-fill${over ? ' over' : ''}`} />
      </div>
      {showTick && (
        <div className="viz-tick-row" aria-hidden="true">
          <span className="viz-tick" style={{ left: `${(fraction * 100).toFixed(2)}%` }} />
        </div>
      )}
      <p className="text-label viz-muted" data-status={status}>
        {typeof note === 'function' ? note(status) : note ?? paceNote(status, spent, usualMonth)}
      </p>
    </div>
  );
}

/** V-04 one row: name, amount, share, and a bar the screen reader skips. */
export function BreakdownRow({ row }) {
  return (
    <li className="viz-breakdown-row">
      <span className="viz-sr">{breakdownWords(row)}</span>
      <div aria-hidden="true">
        <div className="viz-labels text-body">
          <span className="viz-grow">{row.name}</span>
          <span>{dollars(row.amount)}</span>
          <span className="text-label viz-muted viz-share">{row.share}%</span>
        </div>
        <div className="viz-track">
          <Fill percent={row.bar * 100} className="viz-fill" />
        </div>
      </div>
    </li>
  );
}

/**
 * V-04 Category breakdown: the top five, then Everything else. With fewer
 * than 14 days of transactions since she connected, it says it is early days.
 */
export function Breakdown({ items, daysOfData, label = 'Spending by category' }) {
  const rows = breakdownRows(items);
  if (!rows.length) return <p className="text-body viz-muted">Nothing spent yet this month.</p>;
  const thin = Number.isFinite(daysOfData) && daysOfData < THIN_DAYS;
  return (
    <div className="viz-breakdown">
      {thin && (
        <p className="text-label viz-muted">
          Early days: this is {daysOfData === 1 ? '1 day' : `${daysOfData} days`} of spending,
          so the shares will settle as more comes in.
        </p>
      )}
      <ul className="viz-list" aria-label={label}>
        {rows.map((r) => <BreakdownRow key={r.name} row={r} />)}
      </ul>
    </div>
  );
}

/**
 * V-05 What-if slider: a native range input in $10 steps. Arrow keys move
 * $10 and Page Up/Down $50, handled here so every browser agrees.
 * `bounds` comes from sliderBounds(); with none (pace 0 or less) there is no
 * slider at all.
 */
export function Slider({ id, value, bounds, onChange, valueText, label, className = '' }) {
  if (!bounds) return null;
  const pct = sliderPercent(value, bounds);
  return (
    <input id={id} type="range" className={`viz-slider ${className}`.trim()}
           min={bounds.min} max={bounds.max} step={bounds.step} value={value}
           aria-label={label} aria-valuetext={valueText}
           style={{ '--viz-fill': `${pct.toFixed(2)}%` }}
           onChange={(e) => onChange(Number(e.target.value))}
           onKeyDown={(e) => {
             const next = sliderKey(e.key, value, bounds);
             if (next == null) return;
             e.preventDefault();
             if (next !== value) onChange(next);
           }} />
  );
}
