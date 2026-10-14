import { money } from '../api.js';

// Growth › Insights (THL-186 GR-24 to GR-27, THL-196 GR-28 to GR-32): the
// words and the geometry, kept apart from React so each rule can be tested on
// its own. The server sends money in cents (finance/growth_insights.py);
// nothing here ever shows a minus sign, $0, NaN or an empty chart.

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                'September', 'October', 'November', 'December'];

/** "September" from "2026-09". */
export const monthFull = (ym) => MONTHS[Number(ym?.slice(5, 7)) - 1] ?? '';
/** "Sep". */
export const monthShort = (ym) => monthFull(ym).slice(0, 3);
/** "September 2026". */
export const monthYear = (ym) => `${monthFull(ym)} ${ym.slice(0, 4)}`;
/** "Oct 1" from "2026-10-01". */
export const dayShort = (iso) => `${monthShort(iso)} ${Number(iso.slice(8, 10))}`;
/** "October 12". */
export const dayLong = (iso) => `${monthFull(iso)} ${Number(iso.slice(8, 10))}`;
/** A bar's month: "Sep", or "Oct so far" while it's still going. */
export const barMonth = (ym, running) => (running ? `${monthShort(ym)} so far` : monthShort(ym));

/** Whole dollars from cents, never signed: "$1,240". */
export const cash = (c) => money(Math.round(Math.abs(c ?? 0) / 100));
/** Dollars and cents from cents: "$16.49". */
export const cashCents = (c) => money(Math.abs(c ?? 0) / 100, { cents: true });

/** "Sep, Oct and Nov" / "September and October". */
export function listWords(items) {
  if (items.length < 2) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** "a category" counts: "1 subscription", "7 subscriptions". */
export const count = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A month after or before: addMonths('2026-10', -1) is '2026-09'. */
export function addMonths(ym, n) {
  const total = Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1 + n;
  return `${String(Math.floor(total / 12)).padStart(4, '0')}-${String((total % 12) + 1).padStart(2, '0')}`;
}

// ── Tiles (GR-28) ─────────────────────────────────────────────────────────

/** The four tiles: label, figure and the line under it. No tile says $0. */
export function tileRows(d, lens = 'need') {
  const t = d.tiles;
  const [a, b] = lens === 'kind'
    ? [['fixed', 'Fixed', t.fixed ?? 0], ['variable', 'Variable', t.variable ?? 0]]
    : [['essentials', 'Essentials', t.essentials], ['lifestyle', 'Lifestyle', t.lifestyle]];
  const so = d.running ? 'So far' : `In ${monthFull(d.month)}`;
  const arrived = t.arrived ?? [];
  const income = t.estimate ? 'What you told Pearl'
    : t.income > 0
      ? arrived.length === 1 ? `Arrived ${dayShort(arrived[0])}`
        : arrived.length > 1 ? `${arrived.length} payments, latest ${dayShort(arrived[arrived.length - 1])}`
          : 'Arrived'
      : d.running ? 'Nothing has arrived yet' : 'None arrived';
  return [
    { key: 'income', label: 'Income', value: t.income > 0 ? cash(t.income) : 'None yet', note: income },
    { key: a[0], label: a[1], value: a[2] > 0 ? cash(a[2]) : 'Nothing yet', note: so },
    { key: b[0], label: b[1], value: b[2] > 0 ? cash(b[2]) : 'Nothing yet', note: so },
    { key: 'set_aside', label: 'Set aside', value: t.set_aside > 0 ? cash(t.set_aside) : 'Nothing yet',
      note: 'Anchor and chests' },
  ];
}

// ── Compared with your usual (GR-24) ─────────────────────────────────────

/**
 * SnapshotBar props for a group or category against usual, by today: the
 * fill is spent ÷ usual and the tick is where she usually is by today.
 */
export function usualBar(row, d) {
  const spent = row.spent / 100;
  const usual = row.usual / 100;
  const byToday = row.by_today == null ? null : row.by_today / 100;
  const today = dayLong(d.today);
  return {
    category: row.label ?? row.category,
    spent, usualMonth: usual, usualByToday: byToday,
    day: d.day, daysInMonth: d.days_in_month, monthsOfHistory: d.usual.months.length,
    value: spent > 0 ? `${cash(row.spent)} of a usual ${cash(row.usual)}` : `Nothing yet of a usual ${cash(row.usual)}`,
    note: (status) => {
      const by = byToday ?? (usual * d.day) / d.days_in_month;
      const gap = Math.round(Math.abs(spent - by)) * 100;
      if (status === 'over-month') return `${cash((spent - usual) * 100)} over a usual month`;
      if (status === 'over') return gap >= 100 ? `${cash(gap)} more than usual by now` : 'A little above usual by now';
      if (status === 'under') return gap >= 100 ? `${cash(gap)} less than usual by now` : 'A little under usual by now';
      return `About where you usually are by ${today}`;
    },
  };
}

/** GR-25's words column. */
export function compareText(words) {
  if (!words || words.kind === 'new') return 'New this month';
  if (words.kind === 'same') return 'Same as usual';
  return `${cash(words.diff)} ${words.kind} than usual`;
}

/** The category "By category" opens on: furthest above its usual, else the largest. */
export function topCategory(categories) {
  const live = (categories ?? []).filter((c) => c.spent > 0 || c.usual);
  if (!live.length) return null;
  const gap = (c) => c.spent - (c.by_today ?? c.usual ?? 0);
  const above = live.filter((c) => c.usual && gap(c) > 0).sort((a, b) => gap(b) - gap(a));
  return (above[0] ?? live[0]).category;
}

// ── Spending trend (GR-29) ───────────────────────────────────────────────

/** The sentence over the trend: how each group sat against usual. */
export function trendSentence(trend, span) {
  const shown = trend.months.slice(-span).map((m) => m.month);
  const said = ['essentials', 'lifestyle'].map((g) => {
    const label = g === 'essentials' ? 'Essentials' : 'Lifestyle';
    const above = (trend.above?.[g] ?? []).filter((m) => shown.includes(m)).map(monthFull);
    if (!above.length) return `${label} stayed close to your usual.`;
    return `${label} went above your usual in ${listWords(above)}.`;
  });
  return said.join(' ');
}

/** The line under the trend: the usual band, and the months above it. */
export function bandWords(trend, span) {
  if (!trend.band) return 'Your usual month appears once a full month is in.';
  const { low, high } = trend.band;
  const range = Math.round(low / 1000) === Math.round(high / 1000) || low === high
    ? `about ${cash(trend.band.usual)}` : `${cash(low)} to ${cash(high)}`;
  const above = trend.months.slice(-span).filter((m) => m.above).map((m) => monthFull(m.month));
  const tail = above.length
    ? ` ${listWords(above)} ${above.length === 1 ? 'is' : 'are'} above it; nothing else stands out.`
    : '';
  return `Your usual month is ${range}.${tail}`;
}

/** The last full month in the trend, for "Review September". */
export function lastFullMonth(d) {
  const full = d.trend.months.filter((m) => !m.running);
  return full.length ? full[full.length - 1].month : null;
}

// ── Money in and out (GR-31) ─────────────────────────────────────────────

export function keptSentence(rows) {
  const ended = rows.filter((r) => r.kept !== null && (r.income > 0 || r.spent > 0));
  if (!ended.length) return 'What you kept shows here once a month ends.';
  const kept = ended.filter((r) => r.kept > 0);
  if (kept.length === ended.length) {
    return ended.length === 1 ? `You kept some of your income in ${monthFull(ended[0].month)}.`
      : `You kept some of your income every month since ${monthFull(ended[0].month)}.`;
  }
  if (!kept.length) return 'Lately, everything that came in has gone out again.';
  return `You kept some of your income in ${kept.length} of the last ${count(ended.length, 'month')}.`;
}

/** One month in "What you kept": a figure, a dash while it runs, or words. */
export function keptWords(r) {
  if (r.kept === null) return { value: '—', sr: 'still going' };
  if (r.kept > 0) return { value: cash(r.kept), sr: cash(r.kept) };
  if (r.kept === 0) return { value: 'Nothing', sr: 'nothing kept' };
  return { value: 'Nothing', sr: `${cash(r.kept)} more went out than came in`, more: cash(r.kept) };
}

// ── Your savings (GR-32) ─────────────────────────────────────────────────

export function savingsWords(s, { long = false } = {}) {
  const where = s.anchor_started ? 'In your Anchor and treasure chests' : 'In your treasure chests';
  if (long) return s.first ? `${where}, since you joined in ${monthFull(s.first)}.` : `${where}.`;
  if (s.change == null || !s.since) return `${where}.`;
  if (s.change > 0) return `${where}. Up ${cash(s.change)} since ${monthFull(s.since)}.`;
  if (s.change < 0) return `${where}. ${cash(s.change)} used since ${monthFull(s.since)}.`;
  return `${where}. The same as at the end of ${monthFull(s.since)}.`;
}

// ── Where the month went (GR-30) ─────────────────────────────────────────

/**
 * Each group's rows for the list: its four largest and the rest as
 * "Everything else" (a single leftover row keeps its own name).
 */
export function groupRows(group, top = 4) {
  const cats = group.categories;
  if (cats.length <= top + 1) return cats.map((c) => ({ ...c, name: c.category }));
  const rest = cats.slice(top);
  return [
    ...cats.slice(0, top).map((c) => ({ ...c, name: c.category })),
    { name: 'Everything else', category: null, group: group.key, other: true,
      amount: rest.reduce((t, c) => t + c.amount, 0),
      share: rest.reduce((t, c) => t + c.share, 0),
      unsure: rest.reduce((t, c) => t + c.unsure, 0) },
  ];
}

/** GR-28's short list: the three largest, then Everything else. */
export function topRows(where, top = 3) {
  const all = where.groups.flatMap((g) => g.categories.map((c) => ({ ...c, name: c.category, group: g.key })))
    .sort((a, b) => b.amount - a.amount);
  if (all.length <= top + 1) return all;
  const rest = all.slice(top);
  return [...all.slice(0, top), { name: 'Everything else', category: null, other: true, group: null,
    amount: rest.reduce((t, c) => t + c.amount, 0), unsure: rest.reduce((t, c) => t + c.unsure, 0) }];
}

export function unsureWords(where) {
  const cats = where.groups.flatMap((g) => g.categories).filter((c) => c.unsure > 0);
  if (!cats.length) return null;
  const n = cats.reduce((t, c) => t + c.unsure, 0);
  const names = listWords(cats.map((c) => c.category));
  return `${names} ${cats.length === 1 ? 'includes' : 'include'} ${count(n, 'purchase')} Pearl isn’t sure about. Confirm them and this updates.`;
}

export const whereTitle = (month, running) =>
  (running ? `Where ${monthFull(month)} has gone so far` : `Where ${monthFull(month)} went`);

// ── Chart geometry ───────────────────────────────────────────────────────

/** A top for a bar scale: the largest value, with room above it. */
export function scaleMax(values, pad = 1.08) {
  const max = Math.max(0, ...values.filter(Number.isFinite));
  return max > 0 ? max * pad : 0;
}

/** A bar with rounded top corners as an SVG path. */
export function roundedTop(x, y, w, h, r = 8) {
  if (h <= 0 || w <= 0) return '';
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

/** Donut segments as arc paths, clockwise from 12 o'clock. */
export function donutArcs(values, { size = 160, thickness = 32, gap = 0.012 } = {}) {
  const total = values.reduce((t, v) => t + Math.max(v, 0), 0);
  if (!(total > 0)) return [];
  const r = size / 2;
  const inner = r - thickness;
  const point = (rad, a) => [r + rad * Math.sin(a), r - rad * Math.cos(a)];
  let start = 0;
  return values.map((v) => {
    const share = Math.max(v, 0) / total;
    const a0 = start * 2 * Math.PI;
    const a1 = (start + share) * 2 * Math.PI;
    start += share;
    if (share <= 0) return '';
    if (share >= 0.9999) {
      // A full ring: two halves, since one arc can't start and end in one place.
      return `M${r},${r - r}A${r},${r} 0 1 1 ${r},${r + r}A${r},${r} 0 1 1 ${r},0Z`
        + `M${r},${r - inner}A${inner},${inner} 0 1 0 ${r},${r + inner}A${inner},${inner} 0 1 0 ${r},${r - inner}Z`;
    }
    const g = Math.min(gap * 2 * Math.PI, (a1 - a0) / 4);
    const [x0, y0] = point(r, a0 + g / 2);
    const [x1, y1] = point(r, a1 - g / 2);
    const [x2, y2] = point(inner, a1 - g / 2);
    const [x3, y3] = point(inner, a0 + g / 2);
    const large = a1 - a0 - g > Math.PI ? 1 : 0;
    const f = (n) => Number(n.toFixed(2));
    return `M${f(x0)},${f(y0)}A${r},${r} 0 ${large} 1 ${f(x1)},${f(y1)}`
      + `L${f(x2)},${f(y2)}A${inner},${inner} 0 ${large} 0 ${f(x3)},${f(y3)}Z`;
  });
}

/**
 * Stacked areas, bottom up: each layer's polygon between the running total
 * below it and the one including it. `layers` is [[value per point], …].
 */
export function stackedAreas(layers, width, height, max) {
  const n = layers[0]?.length ?? 0;
  if (!n || !(max > 0)) return [];
  const x = (i) => (n === 1 ? width / 2 : (i * width) / (n - 1));
  const y = (v) => height - (v / max) * height;
  const below = new Array(n).fill(0);
  return layers.map((layer) => {
    const lower = [...below];
    const upper = layer.map((v, i) => lower[i] + Math.max(v, 0));
    upper.forEach((v, i) => { below[i] = v; });
    const top = upper.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const bottom = lower.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse();
    return { d: `M${top.join('L')}L${bottom.join('L')}Z`, top: upper.map((v, i) => [x(i), y(v)]) };
  });
}
