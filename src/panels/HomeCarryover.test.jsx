import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CarryoverPrompt, ShortfallSheet, carryoverRow } from './HomeCarryover.jsx';
import { heroCopy, homeAlert, sheetRows } from './HomePanel.jsx';

const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/NaN|undefined|null/);
};

const usual = {
  month: '2026-10', today: '2026-10-09', days_left: 23, next_pay: null, state: 'ok',
  income_source: 'usual', estimate: 'usual', amount: 2984.5, shown: 2980, per_day: 129.56,
  usual: { average: 3900, months: ['2026-07', '2026-08', '2026-09'] },
  rows: [
    { key: 'income', amount: 3900, paycheques: 0, payer: '', source: 'usual', lines: [] },
    { key: 'bills', amount: 600, count: 1, first: null, last: null, lines: [] },
    { key: 'spent', amount: 65.5, pending: 0, lines: [] },
    { key: 'carryover', amount: 250, kind: 'short', lines: [],
      parts: [{ from: '2026-09', amount: 250, kind: 'short', index: 1, of: 2 }] },
  ],
};

describe('expected income from her usual months', () => {
  it('says the number comes from her usual income, and which months', () => {
    const c = heroCopy(usual);
    expect(c.pill).toBe('Estimate');
    expect(c.figure).toBe('$2,980');
    expect(c.context).toBe('Based on your usual income, the average of July, August and September');
    const [income] = sheetRows(usual).rows;
    expect(income.detail).toBe('Your usual income: the average of July, August and September');
  });

  it('offers her own amount', () => {
    const a = homeAlert(usual, { kind: 'irregular', history_days: 120 });
    expect(a.action).toBe('Use a different amount');
    expect(a.text).toContain('the average of July, August and September');
  });
});

describe('last month carried in (THL-212)', () => {
  it('the sheet names it and still adds up', () => {
    const { rows, total } = sheetRows(usual);
    const carry = rows.find((r) => r.key === 'carryover');
    expect(carry.label).toBe('Catching up from September');
    expect(carry.detail).toBe('1 of 2 · you chose to spread it');
    expect(carry.display).toBe('$250.00');
    const [income, ...out] = rows.map((r) => Math.round(r.amount * 100));
    expect(income - out.reduce((x, y) => x + y, 0)).toBe(Math.round(usual.amount * 100));
    expect(total.amount).toBe(usual.amount);
  });

  it('money to spare reads as left over', () => {
    expect(carryoverRow({ kind: 'spare', parts: [{ from: '2026-09', index: 1, of: 1 }] }))
      .toEqual({ label: 'Left over from September', detail: 'Money to spare from September' });
  });

  const short = { month: '2026-09', kind: 'short', amount: 500, income: 4500, spent: 5000,
                  saved: 0, choice: null, auto: false, deadline: null };
  const spare = { month: '2026-09', kind: 'spare', amount: 500, choice: null, auto: false,
                  deadline: '2026-10-09' };

  it('a shortfall asks how October makes it up', () => {
    const out = html(<CarryoverPrompt c={short} onAnswer={() => Promise.resolve()} />);
    expect(out).toContain('September ended $500 short of plan. Choose how October makes it up.');
    const sheet = html(<ShortfallSheet c={short} now="October" was="September"
                                       onClose={() => {}} onAnswer={() => Promise.resolve()} />);
    for (const t of ['Take it from October', 'Spread over 2 months', 'Spread over 3 months',
                     '$4,500 came in and $5,000 went out', 'easy to make up']) {
      expect(sheet).toContain(t);
    }
    calm(sheet);
  });

  it('money to spare suggests saving it, with the date it’s added by', () => {
    const out = html(<CarryoverPrompt c={spare} onAnswer={() => Promise.resolve()} />);
    expect(out).toContain('September left you $500 more than planned');
    expect(out).toContain('Add to your Anchor');
    expect(out).toContain('Put it in a treasure chest');
    expect(out).toContain('Spend it in October');
    expect(out).toContain('If you don’t choose by Friday, October 9, it’s added to October’s safe to spend.');
    expect(out).not.toMatch(/pk-btn primary/);
  });

  it('added after 7 days says so once', () => {
    const out = html(<CarryoverPrompt c={{ ...spare, auto: true, choice: 'spend' }}
                                      onAnswer={() => Promise.resolve()} />);
    expect(out).toContain('September’s $500 to spare is in October’s safe to spend.');
    expect(html(<CarryoverPrompt c={{ ...short, choice: 'now' }} />)).toBe('');
  });
});
