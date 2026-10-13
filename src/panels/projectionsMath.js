import { cash, dayLong, monthFull, monthShort } from './insightsMath.js';

// Growth › Projections (THL-197 GR-33 to GR-36) and the growth calculator
// (THL-135 GR-17, GR-18): the words and the arithmetic, kept apart from React
// so each rule can be tested on its own. The server sends cents
// (finance/look_ahead.py). Every projection is a range; nothing here ever
// shows a minus sign, $0, NaN or undefined.

export { cash };

/** "October 2027" from "2027-10". */
export const monthYear = (ym) => `${monthFull(ym)} ${ym.slice(0, 4)}`;
/** "Oct ’27". */
export const monthTick = (ym) => `${monthShort(ym)} ’${ym.slice(2, 4)}`;
/** "October 31" for the last day of a month. */
export const lastDay = (month, days) => dayLong(`${month}-${String(days).padStart(2, '0')}`);

/** "$180 to $420", or "about $300" when both ends meet. */
export function rangeWords(r) {
  if (!r) return '';
  if (r.low === r.high) return `about ${cash(r.low)}`;
  if (r.low <= 0) return `up to ${cash(r.high)}`;
  return `${cash(r.low)} to ${cash(r.high)}`;
}

/** "March and June 2027", or "December 2026 and March 2027". */
export function monthsBetween(from, to) {
  if (from === to) return monthYear(from);
  if (from.slice(0, 4) === to.slice(0, 4)) return `${monthFull(from)} and ${monthYear(to)}`;
  return `${monthYear(from)} and ${monthYear(to)}`;
}

// ── Your Anchor (GR-33) ──────────────────────────────────────────────────

/** The Anchor line: what it says and where its link goes. */
export function anchorLine(a) {
  if (!a || a.state === 'not_started') {
    return { text: 'Not started yet', link: 'Start your Anchor', view: 'start' };
  }
  if (a.state === 'full') return { text: 'Full', link: 'See your Anchor', view: 'anchor' };
  if (a.state === 'range') {
    return { text: `Likely full between ${monthsBetween(a.from, a.to)}`, link: 'See the projection',
             view: 'projection' };
  }
  return { text: 'No date yet: nothing put aside lately', link: 'See the projection',
           view: 'projection' };
}

// ── This month (GR-34) ───────────────────────────────────────────────────

/** GR-33's line on the This month card. */
export function forecastLine(f) {
  const end = lastDay(f.month, f.days_in_month);
  if (f.state === 'none') return 'Nothing spent yet this month. Your forecast appears as it goes on.';
  if (f.state === 'no_income') return `Likely ${rangeWords(f.spend)} spent by ${end}.`;
  if (f.state === 'over') {
    return `At this pace, likely ${rangeWords({ low: -f.left.high, high: -f.left.low })} more than you can spend by ${end}.`;
  }
  if (f.state === 'tight') {
    return `Likely close to what you can spend by ${end}: up to ${cash(f.left.high)} left.`;
  }
  return `Likely ${rangeWords(f.left)} of safe-to-spend left on ${end}.`;
}

/** GR-34's sentence over the chart. */
export function forecastSentence(f) {
  if (f.state === 'none') return 'Nothing spent yet this month. Your forecast appears as the month goes on.';
  const pace = f.rest.basis === 'this_month' ? 'At this month’s pace so far' : 'At your usual pace';
  const spend = `${pace} you’ll likely spend ${rangeWords(f.spend)} this month.`;
  if (f.state === 'no_income') return `${spend} Add your income to see what that leaves.`;
  if (f.state === 'over') {
    return `${spend} That’s ${rangeWords({ low: -f.left.high, high: -f.left.low })} more than you can spend.`;
  }
  if (f.state === 'tight') return `${spend} That’s close to what you can spend: up to ${cash(f.left.high)} left.`;
  return `${spend} That leaves ${rangeWords(f.left)} of safe-to-spend.`;
}

/** "How we worked this out": the parts of the forecast, in order. */
export function forecastParts(f) {
  const rows = [
    { label: 'Spent so far', value: f.spent > 0 ? cash(f.spent) : 'Nothing yet' },
    { label: 'Bills still to come', value: f.bills > 0 ? cash(f.bills) : 'None this month' },
    { label: f.rest.basis === 'usual'
      ? `The rest of the month, from ${f.rest.months.map(monthFull).join(', ')}`
      : 'The rest of the month, at this month’s pace',
    value: f.rest.high > 0 ? rangeWords(f.rest) : 'Nothing more' },
    { label: 'Likely spent by the end', value: rangeWords(f.spend), strong: true },
  ];
  if (f.can_spend != null) {
    rows.push({ label: 'What you can spend this month', value: cash(f.can_spend) });
  }
  return rows;
}

// ── The next 30 days (GR-35) ─────────────────────────────────────────────

/** "Lowest point about $1,060 on October 31, the day before payday." */
export function next30Line(n, { long = false } = {}) {
  if (n.state === 'no_balance') {
    return n.events.length
      ? 'Add your chequing balance in Profile › Accounts to see where it’s heading.'
      : 'Nothing coming up that we know of yet.';
  }
  const when = `${dayLong(n.lowest.date)}${n.lowest.before_payday ? ', the day before payday' : ''}`;
  if (n.state === 'short') {
    return long
      ? `Your balance may run low around ${when}. Moving a bill or two could help.`
      : `It may run low around ${when}.`;
  }
  const amount = n.lowest.amount > 0 ? `about ${cash(n.lowest.amount)}` : 'close to empty';
  return long
    ? `Your lowest point is likely ${amount} on ${when}. Everything coming up is covered.`
    : `Lowest point ${amount} on ${when}.`;
}

/** A row of "Coming up": "Oct 18  Phone", "$65". */
export function comingUp(n) {
  return n.events.map((e) => ({
    ...e,
    day: `${monthShort(e.date)} ${Number(e.date.slice(8, 10))}`,
    name: e.kind === 'payday' ? 'Payday' : e.label,
    unconfirmed: e.kind === 'bill' && !e.confirmed,
    value: cash(e.amount),
  }));
}

// ── Savings in a year (GR-36) ────────────────────────────────────────────

const floorTo = (c, step) => Math.floor(c / step) * step;
const ceilTo = (c, step) => Math.ceil(c / step) * step;

/** The range in a year with `extra` dollars more a month, as the server
 * works it out (look_ahead.savings_in_a_year), so the slider is instant. */
export function savingsAt(s, extra = 0) {
  const add = Math.max(Math.round(extra * 100), 0);
  const low = s.pace ? s.pace.low : 0;
  const high = s.pace ? s.pace.high : 0;
  const lowC = floorTo(s.now + 12 * (low + add), 10000);
  return { low: lowC, high: Math.max(ceilTo(s.now + 12 * (high + add), 10000), lowC) };
}

/** GR-33's figure and line, and GR-36's sentence. */
export function savingsWords(s, extra = 0) {
  const by = monthYear(s.by);
  const now = savingsAt(s, 0);
  if (s.state !== 'ok' && !(extra > 0)) {
    return {
      figure: s.now > 0 ? cash(s.now) : 'Not yet',
      line: s.state === 'no_pace' ? 'Nothing put aside lately, so there’s no range yet.'
        : 'Once a full month with money moved to savings is in, we’ll show a range.',
      sentence: s.state === 'no_pace'
        ? 'Lately nothing has been put aside, so there’s no range yet. Try saving a bit more below.'
        : 'Once a full month with money moved to savings is in, we’ll show a range.',
    };
  }
  const base = s.state === 'ok'
    ? `At your current pace, likely ${rangeWords(now)} by ${by}.` : `Nothing put aside lately.`;
  const more = extra > 0
    ? ` Saving ${cash(extra * 100)} more a month moves that to ${rangeWords(savingsAt(s, extra))}.` : '';
  return {
    figure: rangeWords(now).replace(/^about /, ''),
    line: `Likely by ${by}, at your current pace.`,
    sentence: base + more,
  };
}

/** The slider's range (THL-57's, from her usual pace): $10 steps, up to
 * about her usual month, never less than $100. */
export function extraBounds(s) {
  const usual = s.pace?.usual ?? 0;
  const max = Math.max(100, Math.round(usual / 1000) * 10);
  return { min: 0, max, step: 10 };
}

// ── The growth calculator (GR-17, GR-18) ─────────────────────────────────

export const RATES = [0.03, 0.05, 0.07];
export const CALC_START = { monthly: '100', years: '10' };

/** "$100" or "100" or "1,250.50" → 100; anything else is null. */
export function parseAmount(text) {
  const n = Number(String(text ?? '').replace(/[$,\s]/g, ''));
  return Number.isFinite(n) && n > 0 && n <= 100000 ? n : null;
}

/** "10 years", "10" → 10; whole years from 1 to 50. */
export function parseYears(text) {
  const n = Number(String(text ?? '').replace(/years?/i, '').trim());
  return Number.isInteger(n) && n >= 1 && n <= 50 ? n : null;
}

/**
 * What `monthly` a month for `years` could become at `rate` a year, added at
 * each month's end and compounded monthly, before fees and taxes. Rounded to
 * the nearest $10, as GR-17 shows it ($100 for 10 years at 3% is $13,970).
 */
export function futureValue(monthly, years, rate) {
  const n = years * 12;
  const r = rate / 12;
  const value = r === 0 ? monthly * n : monthly * ((1 + r) ** n - 1) / r;
  return Math.round(value / 10) * 10;
}

/** GR-17's rows: each rate's figure and how much of its bar is put in vs growth. */
export function calculator(monthly, years) {
  if (monthly == null || years == null) return null;
  const putIn = Math.round(monthly * years * 12);
  const rows = RATES.map((rate) => ({ rate, value: futureValue(monthly, years, rate) }));
  const top = Math.max(...rows.map((r) => r.value), putIn);
  return {
    putIn,
    rows: rows.map((r) => ({
      ...r,
      label: `At ${Math.round(r.rate * 100)}% a year`,
      putInShare: putIn / top,
      growthShare: Math.max(r.value - putIn, 0) / top,
    })),
  };
}

/** Whole dollars, for the calculator (it works in dollars, not cents). */
export const dollarsWords = (n) => cash(Math.round(n) * 100);
