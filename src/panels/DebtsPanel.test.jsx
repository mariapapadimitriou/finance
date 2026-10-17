import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomeBody } from './HomePanel.jsx';
import { DebtsCard, DebtsPage, DetailsPanel, debtLines, parseNumber } from './DebtsPanel.jsx';

// D-02's person (finance/debts.py's tests use the same numbers).
const visa = {
  account_id: 'visa', name: 'TD Visa ••1102', kind: 'card', balance: 1860, rate: 20.99,
  minimum: 55, due_day: 22, due_date: '2026-10-22', before_pearl: 1420,
  before_pearl_at_month_start: 1420, carried: 1420, new_this_month: 440,
};
const loan = {
  account_id: 'loan', name: 'Student loan (NSLSC)', kind: 'student_loan', balance: 3000,
  rate: null, minimum: 120, due_day: 28, due_date: '2026-10-28', before_pearl: null,
  before_pearl_at_month_start: null, carried: 3000, new_this_month: 0,
};
const data = { debts: [loan, visa], count: 2, total: 4860, minimums: 175, missing_details: 1 };

const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null/);
  expect(text).not.toMatch(/overdue|danger|warning|behind on/i);
};

describe('D-02 every debt', () => {
  it('a card: rate, minimum and due date; before Pearl and new, in whole dollars', () => {
    expect(debtLines(visa)).toMatchObject({
      first: '20.99% interest · minimum $55 due October 22',
      second: '$1,420 from before Pearl · $440 new this month, already counted as spending',
      missing: [], action: 'Change the details', kind: 'Credit card',
    });
  });

  it('a loan without a rate says the lender doesn’t share it, and offers to add it', () => {
    expect(debtLines(loan)).toMatchObject({
      first: 'Minimum $120 a month, due on the 28th', second: null,
      missing: ['Your lender doesn’t share the interest rate.'], action: 'Add the rate', kind: 'Loan',
    });
  });

  it('nothing added yet', () => {
    const l = debtLines({ ...loan, minimum: null, due_day: null, due_date: null });
    expect(l.first).toBe(null);
    expect(l.action).toBe('Add the details');
    expect(l.missing).toContain('Add the minimum payment and we’ll count it with your bills.');
  });

  it('a balance carried from last month as well as from before Pearl', () => {
    expect(debtLines({ ...visa, carried: 1620 }).second)
      .toBe('$1,420 from before Pearl · $200 carried from last month · $440 new this month, already counted as spending');
  });

  it('renders the total, the minimums and every debt, calmly', () => {
    const out = html(<DebtsPage data={data} onEdit={() => {}} />);
    expect(out).toContain('Total owed');
    expect(out).toContain('$4,860');
    expect(out).toContain('Minimum payments this month');
    expect(out).toContain('$175');
    expect(out).toContain('Balances aren’t taken out of Allowance; minimum payments are counted as bills.');
    expect(out).not.toMatch(/pk-btn primary/);
    calm(out);
  });

  it('no minimums yet, and no debts at all, in words', () => {
    expect(html(<DebtsPage data={{ ...data, minimums: null }} onEdit={() => {}} />)).toContain('Not added yet');
    const none = html(<DebtsPage data={{ debts: [], count: 0, total: 0, minimums: null }} onEdit={() => {}} />);
    expect(none).toContain('Nothing carried over');
    calm(none);
  });
});

describe('D-01 on Home', () => {
  it('shows the total, says it isn’t taken out, and lists the debts', () => {
    const out = html(<DebtsCard debts={data} onSee={() => {}} />);
    expect(out).toContain('$4,860 across 2. Balances aren’t taken out of Allowance.');
    expect(out).toContain('See debts');
    expect(out).toContain('TD Visa ••1102');
    calm(out);
    expect(html(<DebtsCard debts={{ ...data, debts: [visa], count: 1, total: 1860 }} onSee={() => {}} />))
      .toContain('$1,860 owed.');
  });

  it('only when she has a debt, and last on Home', () => {
    const s = { month: '2026-10', state: 'ok', amount: 642.18, shown: 642.18, per_day: 27.92,
      days_left: 23, estimate: null, rows: [{ key: 'income', amount: 4300, lines: [] }] };
    const ds = { kind: 'normal', history_days: 120, asks_questions: false, answers: {} };
    const out = html(<HomeBody s={s} ds={ds} debts={data} reviewCount={2}
                               onSave={() => Promise.resolve()} onLink={() => {}} />);
    expect(out.indexOf('Debts')).toBeGreaterThan(out.indexOf('need a look'));
    expect(html(<HomeBody s={s} ds={ds} debts={{ ...data, count: 0, debts: [] }}
                          onSave={() => Promise.resolve()} onLink={() => {}} />)).not.toContain('See debts');
  });
});

describe('D-03 add the details', () => {
  it('reads what’s on a statement', () => {
    expect(parseNumber('5.7%')).toBe(5.7);
    expect(parseNumber('$120 a month')).toBe(120);
    expect(parseNumber('')).toBe('');
    expect(parseNumber('about 5')).toBeNaN();
  });

  it('asks for the rate, the minimum and the due day, with one Save', () => {
    const out = html(<DetailsPanel debt={{ ...loan, rate: null, minimum: null }} onClose={() => {}} onSave={() => {}} />);
    expect(out).toContain('Add the details');
    expect(out).toContain('You’ll find these on your latest statement.');
    expect(out).toContain('Interest rate');
    expect(out).toContain('Minimum payment');
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
  });
});
