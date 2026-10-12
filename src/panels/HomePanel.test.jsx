import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HowWeWorkedItOut, SafeToSpendCard, heroCopy, sheetRows } from './HomePanel.jsx';

// The X-01 person on Friday October 9 (finance/safe_to_spend.py's tests use
// the same numbers).
const ok = {
  month: '2026-10', today: '2026-10-09', days_left: 23, next_pay: '2026-10-16',
  income_source: 'detected', state: 'ok', amount: 642.18, per_day: 27.92, over_by: null,
  rows: [
    { key: 'income', amount: 4300, paycheques: 2, payer: 'Northwind Ltd', source: 'detected',
      lines: [
        { label: 'Northwind Ltd', date: '2026-10-01', amount: 2150, arrived: true, kind: 'salary' },
        { label: 'Northwind Ltd', date: '2026-10-16', amount: 2150, arrived: false, kind: 'salary' },
      ] },
    { key: 'bills', amount: 363.48, count: 5, first: '2026-10-12', last: '2026-10-25',
      lines: [
        { label: 'Rogers', date: '2026-10-12', amount: 85, estimate: false, late: false },
        { label: 'Belair Insurance', date: '2026-10-20', amount: 190, estimate: false, late: false },
        { label: 'Hydro One', date: '2026-10-21', amount: 60, estimate: true, late: false },
        { label: 'Netflix', date: '2026-10-22', amount: 16.49, estimate: false, late: false },
        { label: 'Spotify', date: '2026-10-25', amount: 11.99, estimate: false, late: false },
      ] },
    { key: 'spent', amount: 3144.34, pending: 40,
      lines: [{ label: 'Essentials', amount: 2732 }, { label: 'Lifestyle', amount: 412.34 }] },
    { key: 'set_aside', amount: 150, goal: 'saving_goal', target: 300, saved: 150, lines: [] },
  ],
};

const over = {
  ...ok, state: 'over', amount: -84, per_day: null, over_by: 84,
  rows: ok.rows.map((r) => (r.key === 'spent' ? { ...r, amount: 3870.52 } : r)),
};

const needsIncome = { ...ok, state: 'needs_income', amount: null, per_day: null, rows: [] };

const cents = (n) => Math.round(n * 100);
const html = (el) => renderToStaticMarkup(el);
// No minus sign, no $0 on its own, no NaN or undefined anywhere on Home.
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null/);
};

describe('safe-to-spend card', () => {
  it('shows the month’s number in cents and the days left, today included', () => {
    const c = heroCopy(ok);
    expect(c.label).toBe('Safe to spend in October');
    expect(c.figure).toBe('$642.18');
    expect(c.pill).toBe('On track');
    expect(c.context).toBe('23 days left · about $28 a day');
    const out = html(<SafeToSpendCard s={ok} />);
    expect(out).toContain('How we worked this out');
    calm(out);
  });

  it('says how far past the plan, never $0, with the next pay (S1)', () => {
    const c = heroCopy(over);
    expect(c.figure).toBe('$84.00');
    expect(c.figureWords).toBe('past this month’s plan');
    expect(c.context).toContain('Your next pay arrives on Friday, October 16.');
    const out = html(<SafeToSpendCard s={over} />);
    expect(out).toContain('How we worked this out');           // S2: always there
    calm(out);
  });

  it('asks for income instead of guessing (E1)', () => {
    const out = html(<SafeToSpendCard s={needsIncome} />);
    expect(out).toContain('Add your income');
    expect(out).not.toContain('How we worked this out');
    expect(heroCopy(needsIncome).figure).toBeNull();
    calm(out);
  });

  it('a month used up exactly shows no $0', () => {
    const zero = { ...ok, amount: 0, per_day: 0 };
    calm(html(<SafeToSpendCard s={zero} />));
  });

  it('a few dollars over many days doesn’t say "about $0 a day"', () => {
    const tiny = { ...ok, amount: 5, per_day: 0.21 };
    expect(heroCopy(tiny).context).toBe('23 days left');
  });
});

describe('How we worked this out', () => {
  it('adds up to the number shown, to the cent', () => {
    const { rows, total } = sheetRows(ok);
    const [income, ...out] = rows.map((r) => cents(r.amount));
    expect(income - out.reduce((a, b) => a + b, 0)).toBe(cents(ok.amount));
    expect(total.display).toBe(heroCopy(ok).figure);
  });

  it('adds up when past the plan too', () => {
    const { rows, total } = sheetRows(over);
    const [income, ...out] = rows.map((r) => cents(r.amount));
    expect(out.reduce((a, b) => a + b, 0) - income).toBe(cents(over.over_by));
    expect(total.label).toBe('Past this month’s plan');
    expect(total.display).toBe('$84.00');
  });

  it('names every input the way X-01 does, without signs', () => {
    const { rows, total } = sheetRows(ok);
    expect(rows.map((r) => [r.label, r.detail, r.display])).toEqual([
      ['Money coming in this month', '2 paycheques from Northwind Ltd', '$4,300.00'],
      ['Bills still to come', '5 bills between Oct 12 and Oct 25', '$363.48'],
      ['Already spent', 'Includes pending · transfers and card payments don’t count', '$3,144.34'],
      ['Set aside for your saving goal', 'Your monthly goal is $300 · $150 saved so far', '$150.00'],
    ]);
    expect(total.detail).toBe('About $28 a day for 23 days');
    expect(rows[1].lines[2].label).toBe('Hydro One · Oct 21 (estimate)');
    expect(rows[0].lines[1].label).toBe('Northwind Ltd · Oct 16 (on its way)');
  });

  it('a row with nothing in it says so in words', () => {
    const quiet = {
      ...ok,
      rows: ok.rows.map((r) => (r.key === 'bills' ? { ...r, amount: 0, count: 0, lines: [] }
        : r.key === 'set_aside' ? { ...r, amount: 0 } : r)),
    };
    const { rows } = sheetRows(quiet);
    expect(rows.find((r) => r.key === 'bills')).toMatchObject({
      display: 'None', detail: 'Nothing else due this month' });
    expect(rows.find((r) => r.key === 'set_aside').display).toBe('Done');
  });

  it('renders with the sheet’s button secondary (S4) and nothing uncalm', () => {
    for (const s of [ok, over]) {
      const out = html(<HowWeWorkedItOut s={s} onClose={() => {}} onEdit={() => {}} />);
      expect(out).toContain('Got it');
      expect(out).toContain('pk-btn secondary');
      expect(out).not.toContain('pk-btn primary');
      expect(out).toContain('Something look wrong? Edit your income or bills');
      calm(out);
    }
  });
});
