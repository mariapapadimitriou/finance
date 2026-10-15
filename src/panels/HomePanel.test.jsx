import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  HomeBody, HowWeWorkedItOut, IncomePanel, NeedsALook, PathCard, ReconnectPanel, SafeToSpendCard,
  SavingsCard, leftOverFigure, netWords, putAwayWords,
  Snapshot, heroCopy, homeAlert, parseAmount, sheetRows, snapshotRows, stepWords, whenWords,
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
    { key: 'saved', amount: 150, lines: [] },
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
      ['Moved to savings this month', 'What you actually put away. Chests fill from your Anchor, not your month.', '$150.00'],
    ]);
    expect(total.detail).toBe('About $28 a day for 23 days');
    expect(rows[1].lines[2].label).toBe('Hydro One · Oct 21 (estimate)');
    expect(rows[0].lines[1].label).toBe('Northwind Ltd · Oct 16 (on its way)');
  });

  it('a row with nothing in it says so in words', () => {
    const quiet = {
      ...ok,
      rows: ok.rows.map((r) => (r.key === 'bills' ? { ...r, amount: 0, count: 0, lines: [] }
        : r.key === 'saved' ? { ...r, amount: 0 } : r)),
    };
    const { rows } = sheetRows(quiet);
    expect(rows.find((r) => r.key === 'bills')).toMatchObject({
      display: 'None', detail: 'Nothing else due this month' });
    expect(rows.find((r) => r.key === 'saved').display).toBe('Nothing yet');
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

// H-03: income skipped, so the number is from the deposits of 30 days.
const fromDeposits = {
  ...ok, estimate: 'rough', income_source: 'deposits', amount: 627.4, shown: 650, per_day: 28.26,
  next_pay: null,
  rows: [
    { key: 'income', amount: 1230, paycheques: 0, payer: '', source: 'deposits',
      lines: [{ label: 'Client B', date: '2026-10-03', amount: 590, arrived: true, kind: 'other' },
              { label: 'Still expected, from deposits we’ve seen', date: null, amount: 640,
                arrived: false, kind: 'expected' }] },
    { key: 'bills', amount: 557.6, count: 1, first: '2026-10-15', last: '2026-10-15',
      lines: [{ label: 'Rogers', date: '2026-10-15', amount: 557.6, estimate: false, late: false }] },
    { key: 'spent', amount: 45, pending: 0, lines: [{ label: 'Lifestyle', amount: 45 }] },
  ],
};

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
  'H-03 rough, from deposits': [fromDeposits, { ...base, kind: 'learning', history_days: 15 }],
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

// ── Snapshot vs a usual month (THL-48, THL-184), H-01's and H-02's numbers ──

const snap = (rows, extra = {}) => ({
  month: '2026-10', day: 9, days_in_month: 31, months_of_history: 3, curve: 'daily',
  usual_months: ['2026-07', '2026-08', '2026-09'], comparisons_from: '2026-08-01',
  extra_went_to: null, rows, ...extra,
});
const h01 = snap([
  { key: 'income', label: 'Income', received: 2150, expected: 4300, next_pay: '2026-10-16', cautious: null },
  // Rent on the 1st makes her usual Essentials by the 9th most of a month.
  { key: 'essentials', label: 'Essentials', spent: 2732, usual: 2900, usual_by_today: 2700 },
  // $412 against $345 usually by the 9th is 19% ahead: over pace (L2).
  { key: 'lifestyle', label: 'Lifestyle', spent: 412.34, usual: 1150, usual_by_today: 345 },
  { key: 'savings', label: 'Savings', saved: 150, planned: 300, goal: 'anchor' },
]);

describe('snapshot', () => {
  it('reads like H-01, in whole dollars', () => {
    const rows = snapshotRows(h01);
    expect(rows[0]).toMatchObject({ value: '$2,150 of $4,300', note: 'Next pay on Friday, October 16', share: 0.5 });
    expect(rows[1]).toMatchObject({ spent: 2732, usualMonth: 2900, usualByToday: 2700, monthsOfHistory: 3 });
    expect(rows[2]).toMatchObject({ spent: 412, usualMonth: 1150 });
    expect(rows[3]).toMatchObject({ value: '$150 of $300 planned', note: 'Your Anchor', share: 0.5 });
  });

  it('marks over pace in champagne and in words, and on pace calmly (L2)', () => {
    const out = html(<Snapshot snap={h01} />);
    expect(out).toContain('October so far, compared with a usual month');
    expect(out).toContain('Ahead of your usual pace');           // Lifestyle
    expect(out).toContain('About where you usually are');         // Essentials, on its curve
    expect((out.match(/viz-fill over/g) || []).length).toBe(1);
    calm(out);
  });

  it('says how far over a usual month, never in red (H-02)', () => {
    const h02 = snap([...h01.rows.slice(0, 2),
      { key: 'lifestyle', label: 'Lifestyle', spent: 1290, usual: 1150, usual_by_today: 1000 },
      h01.rows[3]], { day: 26 });
    const out = html(<Snapshot snap={h02} />);
    expect(out).toContain('$140 over a usual month');
    calm(out);
  });

  it('all of the pay in, and Savings without a plan (L3)', () => {
    const rows = snapshotRows(snap([
      { key: 'income', label: 'Income', received: 4300, expected: 4300, next_pay: '2026-11-01', cautious: null },
      h01.rows[1], h01.rows[2],
      { key: 'savings', label: 'Savings', saved: 150, planned: null, goal: null },
    ]));
    expect(rows[0].note).toBe('All of this month’s pay is in');
    expect(rows[3]).toMatchObject({ category: 'Put away', value: '$150 this month', share: null,
                                    note: 'Moved to your savings this month' });
  });

  it('cautious income fills against the cautious figure (E4)', () => {
    const [income] = snapshotRows(snap([
      { key: 'income', label: 'Income', received: 1900, expected: 3100, next_pay: null,
        cautious: { lowest: 3100, highest: 4800, month: '2026-07' } },
      ...h01.rows.slice(1)]));
    expect(income.value).toBe('$1,900 so far · usually $3,100 to $4,800');
    expect(income.share).toBeCloseTo(1900 / 3100);
  });

  it('nothing yet, and no usual month yet: words, no $0, no empty bar (E10)', () => {
    const thin = snap([
      { key: 'income', label: 'Income', received: 0, expected: null, next_pay: null, cautious: null },
      { key: 'essentials', label: 'Essentials', spent: 0, usual: 2900, usual_by_today: 2700 },
      { key: 'lifestyle', label: 'Lifestyle', spent: 45, usual: null, usual_by_today: null },
      { key: 'savings', label: 'Savings', saved: 0, planned: null, goal: null },
    ], { months_of_history: 0, comparisons_from: '2026-11-01' });
    const out = html(<Snapshot snap={thin} />);
    expect(out).toContain('Nothing in yet');
    expect(out).toContain('Nothing yet · usually $2,900');
    expect(out).toContain('$45 so far');
    expect(out).toContain('We’ll compare with your usual month from Sunday, November 1.');
    expect(out).toContain('Nothing put away yet this month');
    expect((out.match(/viz-track/g) || []).length).toBe(1);       // only Essentials has a bar
    calm(out);
  });

  it('past the plan, the alert says where the extra went and links there (H-02, C3)', () => {
    const over = { ...ok, state: 'over', over_by: 84, amount: -84, shown: -84 };
    const s2 = { ...h01, extra_went_to: 'Lifestyle' };
    const alert = homeAlert(over, { ...base, kind: 'normal' }, s2);
    expect(alert).toMatchObject({ tone: 'caution', action: 'See where it went', group: 'lifestyle',
                                  text: 'Lifestyle is where the extra went.' });
    const out = html(<HomeBody s={over} ds={{ ...base, kind: 'normal' }} snap={s2}
                               onSave={() => Promise.resolve()} onLink={() => {}} />);
    expect(out).toContain('See where it went');
    expect(out).toContain('compared with a usual month');
  });

  it('the snapshot waits while Pearl is learning (E-02 has its own card)', () => {
    const out = body(...STATES['E-02 learning, answered']);
    expect(out).not.toContain('compared with a usual month');
  });
});

// ── Path card, needs a look, connection health (THL-129, THL-123, THL-120) ──

const buildPath = {
  phase: 'build', step: 1, of: 2, protect_done: true, also: [],
  phases: [{ key: 'protect', label: 'The basics', state: 'done' },
           { key: 'build', label: 'Your Anchor', state: 'now' },
           { key: 'unveil', label: 'Grow your money', state: 'ahead' }],
  steps: [{ key: 'setup', label: 'Set up your Anchor', done: false },
          { key: 'full', label: 'Grow your Anchor to 3 months', done: false, target: null }],
  next: { text: 'Next: set up your Anchor, so a big surprise doesn’t land on your credit card.',
          label: 'Set up your Anchor', action: 'goals' },
};
const tdSignIn = { item_id: 'td', institution: 'TD', state: 'needs_sign_in',
                   last_synced: '2026-10-06T08:00:00', cards_only: true };
const eqDown = { item_id: 'eq', institution: 'EQ Bank', state: 'bank_down',
                 last_synced: '2026-10-09T03:00:00', cards_only: false };
const full = (extra = {}) => html(
  <HomeBody s={ok} ds={{ ...base, kind: 'normal' }} snap={h01} path={buildPath} reviewCount={3}
            today="2026-10-09" onSave={() => Promise.resolve()} onLink={() => {}} {...extra} />);

const wins = { done: 1, of: 6, earned: 1, total: 9, heading: '1 of 6 milestones on your path',
  next: { key: 'anchor_setup', title: 'Next: set up your Anchor',
          line: 'Pick the savings that make up your Anchor. The milestone is 3 months of Essentials.',
          label: 'Set up your Anchor', action: 'goals:start' } };

describe('the next-step card (THL-239 W-01: a small card that links to Wins)', () => {
  it('says the next milestone in her numbers, how far along she is, and holds the one primary', () => {
    const out = full({ wins });
    expect(out).toContain('Your next step');
    expect(out).toContain('See your path');
    expect(out).toContain('>Set up your Anchor</h2>');
    expect(out).toContain('Pick the savings that make up your Anchor.');
    expect(out).toContain('1 of 6 milestones on your path');
    expect(primaries(out)).toBe(1);
    expect(out).toMatch(/pk-btn primary[^>]*>Set up your Anchor/);
    expect(out).not.toMatch(/Protect|Build|Unveil|Shine/);
    calm(out);
  });

  it('stands in with the old path’s next step when Home has no wins summary', () => {
    const out = html(<PathCard path={buildPath} />);
    expect(out).toContain('Set up your Anchor, so a big surprise');
    expect(out).not.toContain('milestones on your path');
  });

  it('every step done', () => {
    expect(stepWords({ ...buildPath, phase: 'unveil', step: null })).toBe('Grow your money · every step done');
    expect(stepWords(buildPath)).toBe('Your Anchor · step 1 of 2');
  });

  it('gives way to the starter questions, which stay the one primary', () => {
    const out = html(<HomeBody s={needsIncome} ds={{ ...base, kind: 'normal', asks_questions: true }}
                               path={{ ...buildPath, phase: 'protect' }}
                               onSave={() => Promise.resolve()} onLink={() => {}} />);
    expect(primaries(out)).toBe(1);
    expect(out).toMatch(/pk-btn primary[^>]*>Save answers/);
  });

  it('is not on Home while Pearl is learning, or with no data', () => {
    for (const k of ['E-02 learning, answered', 'E-01 no data']) {
      const [s, ds] = STATES[k];
      expect(html(<HomeBody s={s} ds={ds} path={buildPath} onSave={() => Promise.resolve()}
                            onLink={() => {}} />)).not.toContain('Your path</p>');
    }
  });
});

describe('needs a look (THL-123)', () => {
  it('counts, explains and links to the queue', () => {
    expect(html(<NeedsALook count={3} />)).toContain('3 transactions need a look');
    expect(html(<NeedsALook count={1} />)).toContain('1 transaction needs a look');
    expect(full()).toContain('Sorting them keeps your numbers right.');
  });

  it('is hidden at 0', () => {
    expect(full({ reviewCount: 0 })).not.toContain('need a look');
  });

  it('shows on E-04 too, but not on E-01', () => {
    const [s, ds] = STATES['E-04 card only'];
    expect(html(<HomeBody s={s} ds={ds} reviewCount={2} onLink={() => {}} />))
      .toContain('2 transactions need a look');
    const [s1, ds1] = STATES['E-01 no data'];
    expect(html(<HomeBody s={s1} ds={ds1} reviewCount={2} onLink={() => {}}
                          onSave={() => Promise.resolve()} />)).not.toContain('need a look');
  });
});

describe('connection health (THL-120)', () => {
  it('C-02: a bank that wants her to sign in again comes first, with Reconnect', () => {
    const over = { ...ok, state: 'over', over_by: 84, amount: -84 };
    const a = homeAlert(over, { ...base, kind: 'normal' }, { ...h01, extra_went_to: 'Lifestyle' },
                        [tdSignIn], null, '2026-10-09');
    expect(a).toMatchObject({ tone: 'caution', action: 'Reconnect' });
    expect(a.text).toBe('TD needs you to sign in again. Card purchases since Tuesday aren’t counted yet.');
  });

  it('C-02: the card says when that bank last updated, and keeps "On track" (C2)', () => {
    const out = full({ connections: [tdSignIn] });
    expect(out).toContain('TD last updated Tuesday');
    expect(out).toContain('On track');
    expect(out).toContain('How we worked this out');
    calm(out);
  });

  it('C-03: a bank that isn’t answering is calm, with nothing to do', () => {
    const a = homeAlert(ok, { ...base, kind: 'normal' }, h01, [eqDown], null, '2026-10-09');
    expect(a).toMatchObject({ tone: 'info', action: 'Details' });
    expect(a.text).toBe('EQ Bank isn’t responding right now. We’ll keep trying; there’s nothing you need to do.');
    expect(full({ connections: [eqDown] })).toContain('EQ Bank last updated today');
  });

  it('C-05: back up to date, said once after reconnecting', () => {
    expect(homeAlert(ok, { ...base, kind: 'normal' }, h01, [], 'TD'))
      .toEqual({ tone: 'positive', text: 'TD is back up to date.' });
  });

  it('C-04: the reconnect panel', () => {
    const out = html(<ReconnectPanel connection={tdSignIn} onClose={() => {}} />);
    expect(out).toContain('Sign in to TD again');
    expect(out).toContain('It’s routine, and nothing is wrong with your account.');
    expect(out).toContain('Continue to TD');
    expect(out).toContain('Not now');
    expect(out).toContain('Pearl stays read-only.');
  });

  it('when words', () => {
    expect(whenWords('2026-10-09T03:00:00', '2026-10-09')).toBe('today');
    expect(whenWords('2026-10-06 08:00:00', '2026-10-09')).toBe('Tuesday');
    expect(whenWords('2026-09-28T08:00:00', '2026-10-09')).toBe('Sep 28');
    expect(whenWords(null, '2026-10-09')).toBe('a while ago');
  });
});

describe('rough estimate (H-03)', () => {
  const ds = STATES['H-03 rough, from deposits'][1];
  const out = html(
    <HomeBody s={fromDeposits} ds={ds} path={buildPath} reviewCount={3} today="2026-10-09"
              onSave={() => Promise.resolve()} onLink={() => {}} />);

  it('says it is rough, from deposits, to the nearest $50', () => {
    const c = heroCopy(fromDeposits);
    expect(c.label).toBe('Safe to spend in October · rough estimate');
    expect(c.pill).toBe('Estimate');
    expect(c.figure).toBe('About $650');
    expect(c.context).toBe('Based on deposits we’ve seen. Add your income for a real number.');
    expect(heroCopy({ ...fromDeposits, shown: 0 }).figure).toBe('Less than $50');
  });

  it('asks for her income once, with nothing to tap in the alert', () => {
    expect(homeAlert(fromDeposits, ds)).toEqual({
      text: 'Tell us what you expect to earn and this number gets much more accurate.' });
    expect(out).toContain('Tell us what you expect to earn and this number gets much more accurate.');
  });

  it('makes "Add your income" the one primary, on the path card', () => {
    expect(primaries(out)).toBe(1);
    expect(out).toMatch(/pk-btn primary[^>]*>Add your income/);
    expect(out).toContain('Your path');
    expect(out).toContain('First, add your income');
    expect(out).toContain('Needed for an accurate safe-to-spend');
    expect(out).toContain('It takes about 30 seconds.');
    expect(out).not.toContain('Monthly take-home pay');              // no starter questions
    expect(out).toContain('3 transactions need a look');
    calm(out);
  });

  it('the sheet names the deposits and what was rounded', () => {
    const { rows, total } = sheetRows(fromDeposits);
    expect(rows[0].detail).toBe('Deposits we’ve seen in the last 30 days');
    expect(total.note).toBe('Shown to the nearest $50, $650.');
  });
});

describe('Savings so far (2026-10-14)', () => {
  const savings = { month: '2026-10',
                    put_away: { contributions: 500, withdrawals: 200, net: 300 },
                    left_over: { income: 4300, spent: 130, net: 4170 } };
  it('shows put away and left over this month, each with what went in', () => {
    const t = html(<SavingsCard savings={savings} />);
    for (const s of ['Savings this month', 'Put away', '$300', '$500 in, $200 taken out',
      'Left over so far', '$4,170', '$4,300 in, $130 spent so far']) {
      expect(t).toContain(s);
    }
    calm(t);
  });
  it('never shows $0, and says when the total dipped below zero', () => {
    expect(netWords(0)).toEqual({ figure: 'Nothing yet', short: false });
    expect(netWords(-40)).toEqual({ figure: '$40', short: true });
    const t = html(<SavingsCard savings={{ ...savings, put_away: { contributions: 0, withdrawals: 40, net: -40 } }} />);
    expect(t).toContain('More taken out than put in');
    calm(t);
    expect(html(<SavingsCard savings={null} />)).toBe('');
    // Chests count as put away, and an estimated income says so.
    expect(putAwayWords({ contributions: 500, chests: 200, withdrawals: 100 }, false))
      .toBe('$500 in, $200 to chests, $100 taken out');
    expect(putAwayWords({ contributions: 0, chests: 0, withdrawals: 0 }, false))
      .toContain('money in your chests');
    const est = html(<SavingsCard savings={{ ...savings, left_over: { ...savings.left_over, estimate: true } }} />);
    expect(est).toContain('$4,300 in (what you told Pearl), $130 spent so far');
    // Below zero reads "$X more out", never red (SV-01).
    const under = html(<SavingsCard savings={{ ...savings, left_over: { income: 2150, spent: 3144, net: -994 } }} nextPay="2026-10-16" />);
    expect(under).toContain('$994 more out');
    expect(under).toContain('Spent more than came in so far. Your next pay lands Friday, October 16.');
    expect(leftOverFigure(0)).toBe('Nothing yet');
  });
});

describe('the snapshot through either lens (2026-10-14)', () => {
  it('shows Essentials and Lifestyle by need, Fixed and Variable by kind', () => {
    const withKinds = { ...h01, rows: [...h01.rows,
      { key: 'fixed', label: 'Fixed', spent: 1800, usual: 1796, usual_by_today: 1796, lens: 'kind' },
      { key: 'variable', label: 'Variable', spent: 1344, usual: 2254, usual_by_today: 1100, lens: 'kind' }] };
    const need = snapshotRows(withKinds, 'need').map((r) => r.key);
    expect(need).toEqual(['income', 'essentials', 'lifestyle', 'savings']);
    const kind = snapshotRows(withKinds, 'kind').map((r) => r.key);
    expect(kind).toEqual(['income', 'savings', 'fixed', 'variable']);
    const out = html(<Snapshot snap={withKinds} />);
    expect(out).toContain('By kind');
    expect(html(<Snapshot snap={h01} />)).not.toContain('By kind');
  });
});

describe('Home reads by the month only (THL-206, THL-235)', () => {
  it('no Month / Week toggle, no week strip, and no afford-it card', () => {
    const out = body(ok, { ...base, kind: 'normal' });
    expect(out).toContain('Safe to spend in October');
    expect(out).not.toMatch(/This week|See week|role="radiogroup"[^>]*Month/);
    expect(out).not.toContain('Can I afford it?');
    expect(out).not.toContain('hm-afford');
  });
});

describe('the calendar strip (THL-245 CAL-06)', () => {
  it('sits under safe to spend and opens the calendar', () => {
    const strip = { month: '2026-10', label: 'October',
                    cells: [{ date: '2026-10-01', day: 1, state: 'on', due: false }],
                    line: 'Next: Netflix on Oct 15, then pay on Oct 16.' };
    const out = html(<HomeBody s={ok} ds={{ ...base, kind: 'normal' }} calendar={strip}
                               onSave={() => Promise.resolve()} onLink={() => {}}
                               onExplain={() => {}} onIncome={() => {}} />);
    expect(out.indexOf('cal-strip')).toBeGreaterThan(out.indexOf('hm-sts'));
    expect(out).toContain('Open calendar');
    expect(out).toContain('Next: Netflix on Oct 15, then pay on Oct 16.');
  });
});
