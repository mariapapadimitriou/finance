import { money } from '../api.js';

// The arithmetic behind the data visualisation patterns (THL-110, V-01 to
// V-05), kept apart from React so each rule can be tested on its own. The
// pictures in viz.jsx only draw what these return.

const clamp = (n, lo, hi) => Math.min(Math.max(n, lo), hi);
const finite = (n) => (Number.isFinite(n) ? n : 0);

/** Whole dollars when the amount is whole, cents when it isn't. */
export const dollars = (n) => money(n, { cents: Math.abs((n ?? 0) % 1) > 0.004 });

// ── Fills (V-01, V-03, V-04) ─────────────────────────────────────────────

/** A share (0–1) as the exact percentage a bar fills, 0 to 100. */
export function fillPercent(share) {
  return clamp(finite(share), 0, 1) * 100;
}

/**
 * The CSS width of a fill. Exactly 0 draws nothing (null); anything above 0
 * shows at least 4px (--space-1) so a small start is still visible.
 */
export function fillWidth(percent) {
  const p = clamp(finite(percent), 0, 100);
  if (p <= 0) return null;
  return `max(var(--space-1), ${Number(p.toFixed(2))}%)`;
}

/**
 * The whole percent said aloud. Never "0" for something that has started, nor
 * "100" for something that hasn't finished.
 */
export function percentWords(percent) {
  const p = clamp(finite(percent), 0, 100);
  if (p > 0 && p < 1) return 1;
  if (p > 99 && p < 100) return 99;
  return Math.round(p);
}

/** "Emergency fund, $3,600 of $6,000, 60 percent". */
export function progressLabel(label, value, percent) {
  return [label, value, `${percentWords(percent)} percent`].filter(Boolean).join(', ');
}

/** The pearl on the Anchor hero grows from 16px to 40px with its progress. */
export function pearlSize(percent) {
  return 16 + 24 * (clamp(finite(percent), 0, 100) / 100);
}

/** "+$300 this month", "$120 used this month" (no minus), "No change this month". */
export function deltaWords(delta) {
  const d = Math.round(finite(delta) * 100) / 100;
  if (d > 0) return { tone: 'positive', text: `+${dollars(d)} this month` };
  if (d < 0) return { tone: 'muted', text: `${dollars(-d)} used this month` };
  return { tone: 'muted', text: 'No change this month' };
}

// ── This month vs usual (V-03) ───────────────────────────────────────────

export const PACE_BAND = 0.10;
export const CURVE_MONTHS = 3;

/**
 * Where she usually is by today, as a share of a usual month (0–1). Her own
 * daily curve when there are at least 3 months of history behind it; the day
 * of the month otherwise.
 */
export function paceFraction({ usualByToday, usualMonth, day, daysInMonth, monthsOfHistory = 0 }) {
  if (monthsOfHistory >= CURVE_MONTHS && usualMonth > 0 && Number.isFinite(usualByToday)) {
    return clamp(usualByToday / usualMonth, 0, 1);
  }
  if (!(daysInMonth > 0)) return 0;
  return clamp(finite(day) / daysInMonth, 0, 1);
}

/** The snapshot fill: spent ÷ usual month, capped at a full bar. */
export function snapshotFill(spent, usualMonth) {
  const s = Math.max(finite(spent), 0);
  if (s <= 0) return 0;
  if (!(usualMonth > 0)) return 1;
  return Math.min(s / usualMonth, 1);
}

/**
 * How this month compares with her usual spend by today:
 * 'over-month' once she has spent more than a usual month, otherwise 'over'
 * or 'under' when more than 10% either side of where she usually is, else 'on'.
 */
export function paceStatus(spent, usualByToday, usualMonth) {
  const s = Math.max(finite(spent), 0);
  if (usualMonth > 0 && s > usualMonth) return 'over-month';
  const by = Math.max(finite(usualByToday), 0);
  if (by <= 0) return s > 0 ? 'over' : 'on';
  const diff = (s - by) / by;
  if (diff > PACE_BAND) return 'over';
  if (diff < -PACE_BAND) return 'under';
  return 'on';
}

/** The words under the snapshot bar. Never colour alone. */
export function paceNote(status, spent, usualMonth) {
  switch (status) {
    case 'over-month': return `${dollars(Math.round((spent - usualMonth) * 100) / 100)} over a usual month`;
    case 'over': return 'Ahead of your usual pace';
    case 'under': return 'A little under your usual pace';
    default: return 'About where you usually are';
  }
}

// ── Date-range projection (V-02) ─────────────────────────────────────────

export const AXIS_MONTHS = 10;

/** "2027-03" → months since year 0, so months can be subtracted. */
export const monthIndex = (ym) => Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1;
/** "2026-11" plus 3 → "2027-02". */
export function addMonths(ym, n) {
  const total = monthIndex(ym) + n;
  return `${String(Math.floor(total / 12)).padStart(4, '0')}-${String((total % 12) + 1).padStart(2, '0')}`;
}

/**
 * Ten months from this one, each Out or part of the likely range:
 * Start / Middle / End, or Single when the range fills one cell. With no
 * range every month is Out. A range running past the axis runs to its edge;
 * a range wholly past it fills only the last month.
 */
export function rangeCells(now, from, to, n = AXIS_MONTHS) {
  const cells = Array.from({ length: n }, (_, i) => ({ month: addMonths(now, i), state: 'out' }));
  if (!now || !from || !to) return cells;
  const base = monthIndex(now);
  let s = monthIndex(from) - base;
  let e = Math.max(monthIndex(to) - base, s);
  if (e < 0) return cells;
  if (s > n - 1) {
    cells[n - 1].state = 'single';
    return cells;
  }
  s = Math.max(s, 0);
  e = Math.min(e, n - 1);
  if (s === e) {
    cells[s].state = 'single';
    return cells;
  }
  for (let i = s; i <= e; i += 1) cells[i].state = i === s ? 'start' : i === e ? 'end' : 'middle';
  return cells;
}

// ── Category breakdown (V-04) ────────────────────────────────────────────

export const TOP_CATEGORIES = 5;
export const THIN_DAYS = 14;

/**
 * Categories sorted by amount, the top five then "Everything else (n)". Each
 * row has its whole-percent share and a bar scaled to the largest row. The
 * shares add up to 100: what rounding leaves over goes to Everything else, or
 * to the largest category when there are five or fewer.
 */
export function breakdownRows(items, top = TOP_CATEGORIES) {
  const spent = (items ?? [])
    .map((c) => ({ name: c.name, amount: finite(c.amount) }))
    .filter((c) => c.amount > 0)
    .sort((a, b) => b.amount - a.amount || String(a.name).localeCompare(String(b.name)));
  const total = spent.reduce((t, c) => t + c.amount, 0);
  if (total <= 0) return [];

  const shown = spent.slice(0, top).map((c) => ({ ...c, other: false }));
  const rest = spent.slice(top);
  if (rest.length) {
    shown.push({
      name: `Everything else (${rest.length})`,
      amount: Math.round(rest.reduce((t, c) => t + c.amount, 0) * 100) / 100,
      other: true,
      count: rest.length,
    });
  }
  for (const r of shown) r.share = Math.round((r.amount / total) * 100);
  const leftover = 100 - shown.reduce((t, r) => t + r.share, 0);
  (rest.length ? shown[shown.length - 1] : shown[0]).share += leftover;

  const largest = Math.max(...shown.map((r) => r.amount));
  for (const r of shown) r.bar = r.amount / largest;
  return shown;
}

/** "Groceries, $412, 20 percent of spending". */
export const breakdownWords = (row) => `${row.name}, ${dollars(row.amount)}, ${row.share} percent of spending`;

// ── What-if slider (V-05) ────────────────────────────────────────────────

export const SLIDER_STEP = 10;
export const SLIDER_PAGE = 50;

/**
 * Where the slider starts and how far it goes: her usual pace rounded to the
 * nearest $10 ($263 → $260), up to about double. It only goes up. No slider
 * (null) when the pace is 0 or less.
 */
export function sliderBounds(usual) {
  if (!(usual > 0)) return null;
  const start = Math.max(SLIDER_STEP, Math.round(usual / SLIDER_STEP) * SLIDER_STEP);
  return { min: start, start, max: start * 2, step: SLIDER_STEP };
}

/** The new value for a key, or null if the slider doesn't handle that key. */
export function sliderKey(key, value, { min, max }) {
  const moves = {
    ArrowRight: SLIDER_STEP, ArrowUp: SLIDER_STEP,
    ArrowLeft: -SLIDER_STEP, ArrowDown: -SLIDER_STEP,
    PageUp: SLIDER_PAGE, PageDown: -SLIDER_PAGE,
  };
  if (key === 'Home') return min;
  if (key === 'End') return max;
  if (!(key in moves)) return null;
  return clamp(value + moves[key], min, max);
}

/** How far along the track a value sits, 0–100. */
export function sliderPercent(value, { min, max }) {
  if (max <= min) return 0;
  return clamp(((value - min) / (max - min)) * 100, 0, 100);
}

// ── The Anchor projection, on the device (port of finance/anchor.py) ─────

/** Python's round(): halves go to the even neighbour. */
export function roundHalfEven(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

/** Whole months to put `toGo` away at `monthly`, or null if never. */
export function monthsTo(toGo, monthly) {
  if (toGo <= 0) return 0;
  if (monthly <= 0) return null;
  return Math.ceil(Number((toGo / monthly).toFixed(6)));
}

const cents = (n) => Math.round(n * 100) / 100;

/**
 * When the Anchor is likely to be full: a range, or honestly no date. The
 * range runs from the best month's pace to the quietest's; `extra` is that
 * much more put aside every month on top of each.
 */
export function projection(toGo, pace, now, extra = 0) {
  if (toGo <= 0) return { state: 'full' };
  if (!pace) return { state: 'none', reason: 'no_history' };
  const best = pace.best.saved + extra;
  const quiet = pace.quietest.saved + extra;
  const usual = pace.usual + extra;
  if (usual <= 0 || best <= 0) return { state: 'none', reason: 'no_pace' };
  const soonest = monthsTo(toGo, best);
  // A quietest month that put nothing away has no date of its own: the far
  // end falls back to the usual pace rather than to never.
  const latest = Math.max(quiet > 0 ? monthsTo(toGo, quiet) : monthsTo(toGo, usual), soonest);
  return {
    state: 'range',
    from: addMonths(now, soonest),
    to: addMonths(now, latest),
    low: cents(quiet),
    high: cents(best),
    usual: cents(usual),
  };
}

/**
 * What putting aside `monthly` would do, as /api/goals/anchor/whatif answers
 * it: the new projection and how many months sooner, measured between the
 * middles of the two ranges.
 */
export function whatIf({ toGo, pace, now, current }, monthly) {
  const usual = pace ? pace.usual : 0;
  let result;
  if (pace) {
    result = projection(toGo, pace, now, monthly - usual);
  } else {
    const soon = monthsTo(toGo, monthly);
    result = soon == null ? { state: 'none', reason: 'no_pace' }
      : { state: 'range', from: addMonths(now, soon), to: addMonths(now, soon) };
  }
  let sooner = null;
  if (current?.state === 'range' && result.state === 'range') {
    const middle = (p) => (monthIndex(p.from) + monthIndex(p.to)) / 2;
    sooner = roundHalfEven(middle(current) - middle(result));
  }
  return { monthly, usual, extra: monthly - usual, projection: result, sooner };
}

/** "About a month sooner", "About 3 months sooner", "About the same time". */
export function soonerWords(n) {
  if (n == null) return '';
  if (n <= 0) return 'About the same time';
  return n === 1 ? 'About a month sooner' : `About ${n} months sooner`;
}

/** The slider's aria-valuetext: "$310 a month, about a month sooner". */
export function sliderWords(monthly, result) {
  const lead = `${dollars(monthly)} a month`;
  if (!result) return lead;
  if (result.projection?.state !== 'range') return `${lead}, still no date`;
  const s = soonerWords(result.sooner);
  return s ? `${lead}, ${s.charAt(0).toLowerCase()}${s.slice(1)}` : lead;
}
