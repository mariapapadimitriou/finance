import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  HomeBody, HowWeWorkedItOut, IncomePanel, SafeToSpendCard, heroCopy, homeAlert, parseAmount,
  sheetRows,
} from './HomePanel.jsx';

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
ok.shown = ok.amount; ok.estimate = null; over.shown = -84; over.estimate = null;

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
    expect(out).toContain('Tell us what you expect to earn');
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

// ── Data states (THL-137 E-01 to E-04; THL-72, THL-69, THL-47, THL-70) ──

const base = { history_days: 120, first_date: '2026-06-01', learning_until: '2026-07-01',
  comparisons_from: '2026-08-01', linking_failed: false, answers: { income: null, rent: null },
  asks_questions: false, spent_so_far: 3144.34, bills_found: 6 };

const rough = {
  ...ok, estimate: 'rough', income_source: 'told', amount: 2605, shown: 2600, per_day: 113.04,
  rows: [
    { key: 'income', amount: 4300, paycheques: 0, payer: '', source: 'told',
      lines: [{ label: 'Still expected this month', date: null, amount: 4300, arrived: false, kind: 'expected' }] },
    { key: 'bills', amount: 1650, count: 1, first: null, last: null,
      lines: [{ label: 'Rent or mortgage', date: null, amount: 1650, estimate: false, late: false, told: true }] },
    { key: 'spent', amount: 45, pending: 0, lines: [{ label: 'Lifestyle', amount: 45 }] },
  ],
};
const cautious = {
  ...ok, estimate: 'cautious', income_source: 'cautious', amount: 2980, shown: 2980, per_day: 129.56,
  cautious: { lowest: 3100, month: '2026-07', highest: 4800, months: [] },
  rows: [
    { key: 'income', amount: 3100, paycheques: 0, payer: '', source: 'cautious',
      cautious: { lowest: 3100, month: '2026-07' },
      lines: [{ label: 'Client B', date: '2026-10-03', amount: 1900, arrived: true, kind: 'other' },
              { label: 'Still expected, being cautious', date: null, amount: 1200, arrived: false, kind: 'expected' }] },
    { key: 'bills', amount: 0, count: 0, first: null, last: null, lines: [] },
    { key: 'spent', amount: 120, pending: 0, lines: [{ label: 'Essentials', amount: 120 }] },
  ],
};

const STATES = {
  'E-01 no data': [needsIncome, { ...base, kind: 'no_data', history_days: 0, first_date: null,
    learning_until: null, comparisons_from: null, spent_so_far: 0, bills_found: 0 }],
  'E-01 linking failed': [needsIncome, { ...base, kind: 'no_data', history_days: 0,
    linking_failed: true, spent_so_far: 0, bills_found: 0 }],
  'E-02 learning, asks': [needsIncome, { ...base, kind: 'learning', history_days: 15,
    learning_until: '2026-10-25', comparisons_from: '2026-11-01', asks_questions: true,
    spent_so_far: 45, bills_found: 0 }],
  'E-02 learning, answered': [rough, { ...base, kind: 'learning', history_days: 15,
    learning_until: '2026-10-25', comparisons_from: '2026-11-01', spent_so_far: 45, bills_found: 0 }],
  'answers without linking': [rough, { ...base, kind: 'learning', history_days: 0,
    first_date: null, learning_until: null, comparisons_from: null, spent_so_far: 0, bills_found: 0 }],
  'E-03 irregular': [cautious, { ...base, kind: 'irregular' }],
  'E-04 card only': [needsIncome, { ...base, kind: 'card_only',
    card_spending: { amount: 740, lines: [{ label: 'Lifestyle', amount: 430 }, { label: 'Essentials', amount: 310 }] } }],
  'E-04 nothing spent yet': [needsIncome, { ...base, kind: 'card_only', spent_so_far: 0,
    card_spending: { amount: 0, lines: [] } }],
  normal: [ok, { ...base, kind: 'normal' }],
  'normal, no income': [needsIncome, { ...base, kind: 'normal', asks_questions: true }],
};

const body = (s, ds) => html(
  <HomeBody s={s} ds={ds} onSave={() => Promise.resolve()} onLink={() => {}}
            onExplain={() => {}} onIncome={() => {}} />);
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;

describe('every data state', () => {
  for (const [name, [s, ds]] of Object.entries(STATES)) {
    it(`${name}: calm, and exactly one primary action at most`, () => {
      const out = body(s, ds);
      calm(out);
      expect(primaries(out)).toBeLessThanOrEqual(1);
    });
  }

  it('E-01 has one primary: link the bank, or try again after a failure', () => {
    const fresh = body(...STATES['E-01 no data']);
    expect(primaries(fresh)).toBe(1);
    expect(fresh).toContain('Link your bank');
    expect(fresh).toContain('Your path');
    expect(fresh).toContain('Prefer to start without linking?');
    const failed = body(...STATES['E-01 linking failed']);
    expect(failed).toContain('Try linking again');
    expect(failed).toContain('Linking didn’t finish last time');
  });

  it('E-02 asks the starter questions, and they are the primary (E3)', () => {
    const out = body(...STATES['E-02 learning, asks']);
    expect(primaries(out)).toBe(1);
    expect(out).toMatch(/pk-btn primary[^>]*>Save answers/);
    expect(out).toContain('Monthly take-home pay');
    expect(out).toContain('Pearl is learning your patterns');
    expect(out).toContain('Sunday, October 25');                  // with a date
    expect(out).toContain('Sunday, November 1');
  });

  it('E-02 answered: a rough estimate, labelled, rounded down to $10', () => {
    const c = heroCopy(rough);
    expect(c).toMatchObject({ pill: 'Estimate', figure: 'About $2,600' });
    expect(c.context).toBe('Rough estimate from the income and rent you told us');
    const out = body(...STATES['E-02 learning, answered']);
    expect(out).not.toContain('Save answers');
    expect(out).toContain('Spent so far');
    expect(out).toContain('None yet');                           // bills found: 0
  });

  it('answers without linking still lead back to linking', () => {
    const out = body(...STATES['answers without linking']);
    expect(primaries(out)).toBe(1);
    expect(out).toContain('Link your bank');
  });

  it('E-03 is cautious, labelled, with "Use a different amount"', () => {
    const c = heroCopy(cautious);
    expect(c).toMatchObject({ pill: 'Cautious', figure: '$2,980' });
    expect(c.context).toBe('Based on your lowest month of the last 3 ($3,100)');
    expect(homeAlert(cautious, STATES['E-03 irregular'][1]).action).toBe('Use a different amount');
    expect(body(...STATES['E-03 irregular'])).toContain('Use a different amount');
  });

  it('E-04 shows spending only, with one prompt to link chequing', () => {
    const out = body(...STATES['E-04 card only']);
    expect(primaries(out)).toBe(1);
    expect(out).toContain('Link your chequing account');
    expect(out).toContain('$740');
    expect(out).not.toContain('Safe to spend in');
    expect(body(...STATES['E-04 nothing spent yet'])).toContain('Nothing yet');
  });

  it('the sheet keeps exact rows and says what was rounded (E5)', () => {
    const { rows, total } = sheetRows(rough);
    expect(total.display).toBe('$2,605.00');
    expect(total.note).toBe('Shown rounded down to $2,600.');
    expect(rows[1].lines[0].label).toBe('Rent or mortgage (what you told us)');
    expect(rows[1].detail).toBe('1 bill');
    const careful = sheetRows(cautious);
    expect(careful.rows[0].detail).toBe('Your lowest month of the last 3 was July, $3,100');
    expect(careful.rows[1].display).toBe('None');
    const out = html(<HowWeWorkedItOut s={rough} onClose={() => {}} onEdit={() => {}} />);
    expect(out).toContain('Safe to spend: about $2,600');
    calm(out);
  });

  it('a rough number under $10 never reads $0', () => {
    const tiny = { ...rough, amount: 7.5, shown: 0, per_day: 0 };
    expect(heroCopy(tiny).figure).toBe('Less than $10');
    calm(html(<SafeToSpendCard s={tiny} />));
  });
});

describe('parseAmount', () => {
  it.each([['3200', 3200], ['$3,200', 3200], ['3,200.50', 3200.5], [' 1650 ', 1650]])(
    '%s → %s', (text, n) => expect(parseAmount(text)).toBe(n));
  it.each(['', 'lots', '-5', '3.333', '12abc'])('%s is not an amount', (text) => {
    expect(Number.isNaN(parseAmount(text))).toBe(true);
  });
});

describe('changing the income (E4)', () => {
  it('offers the way back to the cautious figure once she has overridden it', () => {
    const overridden = { ...cautious, income_source: 'told', estimate: null, overridden: true };
    const out = html(<IncomePanel s={overridden} told={4000} onClose={() => {}}
                                  onSave={() => Promise.resolve()} onReset={() => Promise.resolve()} />);
    expect(out).toContain('value="4000"');
    expect(out).toContain('Go back to the cautious figure ($3,100)');
    calm(out);
  });
});
