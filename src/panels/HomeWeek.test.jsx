import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomeBody } from './HomePanel.jsx';
import {
  AffordCard, WeekSheet, WeekStrip, affordCopy, monthLine, weekHeroCopy, weekLine, weekRange,
  weekSheetRows,
} from './HomeWeek.jsx';

// The X-01 month on Friday October 9, and its week (Oct 5–11). The week and
// the rest of October add up to the month: $105.75 + $536.43 = $642.18.
const ok = {
  month: '2026-10', today: '2026-10-09', days_left: 23, next_pay: '2026-10-16',
  income_source: 'detected', state: 'ok', amount: 642.18, shown: 642.18, per_day: 27.92,
  over_by: null, estimate: null,
  rows: [{ key: 'income', amount: 4300, paycheques: 2, payer: 'Northwind Ltd', source: 'detected', lines: [] }],
};
const over = { ...ok, state: 'over', amount: -84, shown: -84, per_day: null, over_by: 84 };
const week = {
  start: '2026-10-05', end: '2026-10-11', days: 7, days_left: 3,
  at_start: 724.18, share: 187.75, spent: 82, left: 105.75, shown: 105.75, per_day: 35.25,
  state: 'ok', over_by: null, rolled_over: 45, rest_of_month: 536.43, rest_days: 20,
  month_amount: 642.18, estimate: null,
};
const weekOver = { ...week, spent: 1104.34, left: -916.59, shown: -916.59, per_day: null,
  state: 'over', over_by: 916.59, rest_of_month: 1558.77 };
const base = { kind: 'normal', history_days: 120, asks_questions: false, answers: {},
  comparisons_from: '2026-08-01', learning_until: '2026-07-01' };

const cents = (n) => Math.round(n * 100);
const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null/);
};
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;
const home = (extra = {}) => html(
  <HomeBody s={ok} ds={base} week={week} onSave={() => Promise.resolve()} onLink={() => {}}
            onView={() => {}} {...extra} />);

describe('the week (THL-166)', () => {
  it('W-01: a strip under the month, in whole dollars, with what rolled over', () => {
    expect(weekRange(week)).toBe('Oct 5–11');
    expect(weekRange({ ...week, start: '2026-10-31', end: '2026-10-31' })).toBe('Oct 31');
    expect(weekLine(week)).toBe('$106 left · about $35 a day · $45 rolled over');
    const out = home();
    expect(out).toContain('Safe to spend in October');
    expect(out).toContain('This week');
    expect(out).toContain('See week');
    calm(out);
  });

  it('W-02: the week as the main view, with the month in the strip', () => {
    const c = weekHeroCopy(week, ok);
    expect(c).toMatchObject({ label: 'Safe to spend this week', figure: '$105.75', pill: 'On track' });
    expect(c.context).toBe('Oct 5–11 · about $35 a day · includes $45 from earlier weeks');
    expect(monthLine(ok)).toBe('$642.18 left · 23 days');
    const out = home({ view: 'week' });
    expect(out).toContain('Safe to spend this week');
    expect(out).toContain('See month');
    expect(out).toMatch(/role="radio" aria-checked="true"[^>]*>This week/);
    calm(out);
  });

  it('a week past its share says so in words, and the month still leads', () => {
    expect(weekLine(weekOver)).toBe('$917 past this week’s plan');
    const c = weekHeroCopy(weekOver, ok);
    expect(c).toMatchObject({ figure: '$916.59', figureWords: 'past this week’s plan', pill: null });
    expect(c.context).toBe('Oct 5–11 · it comes out of the rest of October');
    expect(monthLine(over)).toBe('$84.00 past this month’s plan');
    calm(html(<WeekStrip view="month" s={ok} w={weekOver} onView={() => {}} />));
  });

  it('rough weeks are rounded down and labelled', () => {
    const rough = { ...week, left: 1072.66, shown: 1070, estimate: 'rough' };
    expect(weekLine(rough)).toMatch(/^About \$1,070 left/);
    expect(weekHeroCopy(rough, ok)).toMatchObject({ figure: 'About $1,070', pill: 'Estimate' });
  });

  it('no number, no toggle and no week (E1)', () => {
    const out = home({ s: { ...ok, state: 'needs_income', amount: null, rows: [] }, week: null });
    expect(out).not.toContain('This week');
    expect(out).not.toContain('Can I afford it?');
  });

  it('keeps Home to one primary action', () => {
    expect(primaries(home())).toBe(0);
    expect(primaries(home({ view: 'week' }))).toBe(0);
  });
});

describe('the weekly working (W-03)', () => {
  it('adds up: the week and the rest of the month make the month, to the cent', () => {
    const { rows, total, adds, sum } = weekSheetRows(week, ok);
    expect(rows.map((r) => r.label)).toEqual(['This week’s share of October', 'Spent so far this week']);
    expect(rows[0].display).toBe('$187.75');
    expect(rows[0].detail).toContain('Includes $45.00 from earlier weeks');
    expect(rows[1].detail).toContain('Bills aren’t counted');
    expect(total).toMatchObject({ label: 'Left this week', display: '$105.75' });
    expect(cents(week.share) - cents(week.spent)).toBe(cents(week.left));
    expect(cents(week.left) + cents(week.rest_of_month)).toBe(cents(ok.amount));
    expect(adds.map((a) => a.label)).toEqual(['Left this week', 'The rest of October (20 days)']);
    expect(sum).toMatchObject({ label: 'Safe to spend in October', display: '$642.18' });
  });

  it('renders calm, without signs, and with a secondary Done (S3, S4)', () => {
    const out = html(<WeekSheet w={week} s={ok} onClose={() => {}} />);
    expect(out).toContain('This week, Oct 5–11');
    expect(out).toMatch(/pk-btn secondary[^>]*>Done/);
    expect(out).not.toMatch(/[+−]\s?\$/);
    calm(out);
    calm(html(<WeekSheet w={weekOver} s={ok} onClose={() => {}} />));
  });

  it('the last week of the month has no "rest of the month"', () => {
    const last = { ...week, start: '2026-10-26', end: '2026-10-31', days: 6, rest_days: 0,
      rest_of_month: 0, left: 642.18 };
    expect(weekSheetRows(last, ok).adds).toHaveLength(1);
  });
});

describe('Can I afford it? (THL-167)', () => {
  const fits = { amount: 180, fits: true, before: 642.18, after: 462.18, per_day_after: 20.09,
    days_left: 23, short_by: null, already_over: false, estimate: null,
    week: { left: 105.75, within: false, left_after: null }, next_month: null };
  const soon = { ...fits, amount: 900, fits: false, after: null, per_day_after: null, short_by: 257.82,
    next_month: { month: '2026-11', fits: true, per_day_after: 24.55 } };
  const saveUp = { ...soon, amount: 5000, short_by: 4357.82,
    next_month: { month: '2026-11', fits: false, per_day_after: null } };

  it('AF-02: it fits, before and after, per day, and one line on the week (A2)', () => {
    const c = affordCopy(fits, ok);
    expect(c.title).toBe('Yes, $180 fits this month.');
    expect(c.lines).toEqual([
      'Safe to spend goes from $642.18 to $462, about $20 a day for the 23 days left.',
      'That’s more than this week’s $106, so the weeks after would have a little less.',
    ]);
    const small = affordCopy({ ...fits, amount: 40, week: { left: 105.75, within: true, left_after: 65.75 } }, ok);
    expect(small.lines[1]).toBe('This week you’d still have $66.');
  });

  it('AF-03: by how much, and November if it looks like a usual month (A1)', () => {
    const c = affordCopy(soon, ok);
    expect(c.title).toBe('Not this month, but soon.');
    expect(c.lines[0]).toBe('$900 is $258 more than what’s left in October. If November looks like a usual month, it would fit then, leaving about $25 a day.');
    expect(c.chest).toBe(true);
  });

  it('more than a usual month leaves: save up, calmly', () => {
    const c = affordCopy(saveUp, ok);
    expect(c.title).toBe('This one needs saving up for.');
    expect(c.lines[0]).toContain('treasure chest');
  });

  it('a month already past its plan', () => {
    const c = affordCopy({ ...soon, already_over: true }, over);
    expect(c.lines[0]).toMatch(/^October’s plan is already used up, so \$900 would come from November\./);
  });

  it('never says no, never shows a sign or $0', () => {
    for (const r of [fits, soon, saveUp]) {
      const c = affordCopy(r, ok);
      const text = [c.title, ...c.lines].join(' ');
      expect(text).not.toMatch(/\bno\b|can’t afford|cannot/i);
      calm(text);
    }
  });

  it('AF-01: one field and a secondary Check', () => {
    const out = html(<AffordCard s={ok} onChest={() => {}} />);
    expect(out).toContain('Can I afford it?');
    expect(out).toContain('It costs');
    expect(out).toMatch(/pk-btn secondary[^>]*>Check/);
    expect(primaries(out)).toBe(0);
  });
});
