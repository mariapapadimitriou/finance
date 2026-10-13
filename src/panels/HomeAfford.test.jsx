import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomeBody } from './HomePanel.jsx';
import { AffordCard, affordCopy } from './HomeAfford.jsx';

// The X-01 month on Friday October 9.
const ok = {
  month: '2026-10', today: '2026-10-09', days_left: 23, next_pay: '2026-10-16',
  income_source: 'detected', state: 'ok', amount: 642.18, shown: 642.18, per_day: 27.92,
  over_by: null, estimate: null,
  rows: [{ key: 'income', amount: 4300, paycheques: 2, payer: 'Northwind Ltd', source: 'detected', lines: [] }],
};
const over = { ...ok, state: 'over', amount: -84, shown: -84, per_day: null, over_by: 84 };
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
  <HomeBody s={ok} ds={base} onSave={() => Promise.resolve()} onLink={() => {}} {...extra} />);

describe('Can I afford it? (THL-167)', () => {
  const fits = { amount: 180, fits: true, before: 642.18, after: 462.18, per_day_after: 20.09,
    days_left: 23, short_by: null, already_over: false, estimate: null,
    week: { left: 105.75, within: false, left_after: null }, next_month: null };
  const soon = { ...fits, amount: 900, fits: false, after: null, per_day_after: null, short_by: 257.82,
    next_month: { month: '2026-11', fits: true, per_day_after: 24.55 } };
  const saveUp = { ...soon, amount: 5000, short_by: 4357.82,
    next_month: { month: '2026-11', fits: false, per_day_after: null } };

  it('AF-02: it fits, before and after, per day, for the month only', () => {
    const c = affordCopy(fits, ok);
    expect(c.title).toBe('Yes, $180 fits this month.');
    expect(c.lines).toEqual([
      'Safe to spend goes from $642.18 to $462, about $20 a day for the 23 days left.',
    ]);
    const small = affordCopy({ ...fits, amount: 40, week: { left: 105.75, within: true, left_after: 65.75 } }, ok);
    expect(small.lines.join(' ')).not.toMatch(/week/i);
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

describe('Home reads by the month only', () => {
  it('no Month / Week toggle, no week strip, and Can I afford it? stays', () => {
    const out = home();
    expect(out).toContain('Safe to spend in October');
    expect(out).not.toMatch(/This week|See week|role="radiogroup"[^>]*Month/);
    expect(out).toContain('Can I afford it?');
    calm(out);
  });
});
