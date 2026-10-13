import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomeBody } from './HomePanel.jsx';
import {
  BudgetsCard, BudgetsPage, ChangeBudget, budgetBar, budgetFor, changeWords,
} from './CategoryBudgetsPanel.jsx';

// B-01's month on October 9, with the server's statuses (finance/category_budgets.py).
const row = (category, extra) => ({
  category, group: 'lifestyle', pct: 100, bill: false, to_come: 0, over_by: null, ...extra,
});
const data = {
  ready: true, month: '2026-10', day: 9, days_in_month: 31, months_of_history: 3, top: 5,
  needs_look: 2,
  rows: [
    row('Groceries', { group: 'essentials', usual: 460, budget: 460, spent: 412, by_today: 132, status: 'over' }),
    row('Shopping', { usual: 233.33, pct: 90, budget: 210, spent: 188, by_today: 61, status: 'over' }),
    row('Dining', { usual: 214, pct: 80, budget: 171.2, spent: 209, by_today: 50, status: 'over-month', over_by: 37.8 }),
    row('Transport', { group: 'essentials', usual: 140, budget: 140, spent: 30, by_today: 40, status: 'under' }),
    row('Streaming', { usual: 64, budget: 64, spent: 64, bill: true, by_today: null, status: 'paid' }),
    row('Insurance', { group: 'essentials', usual: 190, budget: 190, spent: 0, bill: true, by_today: null, status: 'to_come', to_come: 190 }),
    row('Gifts', { usual: 40, budget: 40, spent: 0, by_today: 12, status: 'on' }),
  ],
};
const by = (c) => data.rows.find((r) => r.category === c);

const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null|exceed|danger|red/i);
};

describe('B-01 budgets', () => {
  it('a row is the % of usual and the dollars together, in words', () => {
    const b = budgetBar(by('Dining'), data);
    expect(b.category).toBe('Dining · 80% of usual');
    expect(b.value).toBe('$209 of $171');
    expect(b.note('over-month')).toBe('$38 over this month');
    expect(b.note('over')).toBe('On pace to go over');
    expect(b.note('under')).toBe('On track');
    expect(b.note('on')).toBe('On track');
  });

  it('bills: no tick, "All paid", or what is still to come', () => {
    expect(budgetBar(by('Streaming'), data)).toMatchObject({ note: 'All paid for October', share: 1 });
    expect(budgetBar(by('Insurance'), data)).toMatchObject({
      note: '$190 still to come this month', value: 'Nothing yet of $190' });
  });

  it('renders the five largest, champagne for over, and the rest behind a link', () => {
    const out = html(<BudgetsPage data={data} onChange={() => {}} />);
    expect(out).toContain('Budgets for October');
    expect(out).toContain('Each budget starts at your usual month for that category.');
    expect((out.match(/viz-fill over/g) || []).length).toBe(3);          // Groceries, Shopping, Dining
    expect(out).toContain('Everything else (2 categories)');
    expect(out).not.toContain('Gifts');
    expect((out.match(/>Change/g) || []).length).toBe(5);
    expect(out).not.toMatch(/pk-btn primary/);
    calm(out);
  });

  it('before a full month, says when they start (E2)', () => {
    const out = html(<BudgetsPage data={{ ready: false, starts: '2026-11-01', month: '2026-10', rows: [] }}
                                  onChange={() => {}} />);
    expect(out).toContain('Budgets start after your first full month');
    expect(out).toContain('Sunday, November 1');
    calm(out);
  });
});

describe('B-02 change a budget', () => {
  it('works out the dollars from the %, and says the difference', () => {
    expect(budgetFor(214, 80)).toBe(171.2);
    expect(changeWords(214, 80)).toBe('About $43 less than usual. You can change it any time.');
    expect(changeWords(214, 110)).toBe('About $21 more than usual. You can change it any time.');
    expect(changeWords(214, 100)).toBe('The same as your usual month. You can change it any time.');
  });

  it('presets 70% to 110%, the dollars, and one Save', () => {
    const out = html(<ChangeBudget row={by('Dining')} onClose={() => {}} onSave={() => Promise.resolve()} />);
    expect(out).toContain('Change this budget');
    expect(out).toContain('Your usual month: $214');
    for (const p of ['70%', '80%', '90%', '100%', '110%']) expect(out).toContain(`>${p}<`);
    expect(out).toMatch(/aria-checked="true"[^>]*>80%/);
    expect(out).toContain('$171 a month');
    expect(out).toContain('Use a custom %');
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
  });

  it('a custom % opens on the slider, 50% to 150% in 5s', () => {
    const out = html(<ChangeBudget row={{ ...by('Dining'), pct: 85 }} onClose={() => {}} onSave={() => Promise.resolve()} />);
    expect(out).toContain('Custom: 85% of usual');
    expect(out).toMatch(/type="range" min="50" max="150" step="5"/);
  });
});

describe('B-03 on Home', () => {
  it('counts over and on pace to go over, hidden at 0 (B4)', () => {
    expect(html(<BudgetsCard budgets={{ ready: true, needs_look: 2 }} onSee={() => {}} />))
      .toContain('2 budgets need a look this month.');
    expect(html(<BudgetsCard budgets={{ ready: true, needs_look: 1 }} onSee={() => {}} />))
      .toContain('1 budget needs a look this month.');
    expect(html(<BudgetsCard budgets={{ ready: true, needs_look: 0 }} onSee={() => {}} />)).toBe('');
  });

  it('sits after needs a look and before debts (L1)', () => {
    const s = { month: '2026-10', state: 'ok', amount: 642.18, shown: 642.18, per_day: 27.92,
      days_left: 23, estimate: null, rows: [{ key: 'income', amount: 4300, lines: [] }] };
    const ds = { kind: 'normal', history_days: 120, asks_questions: false, answers: {} };
    const debts = { count: 1, total: 1860, debts: [{ account_id: 'v', name: 'TD Visa', balance: 1860 }] };
    const out = html(<HomeBody s={s} ds={ds} reviewCount={2} budgets={{ ready: true, needs_look: 2 }}
                               debts={debts} onSave={() => Promise.resolve()} onLink={() => {}} />);
    const look = out.indexOf('need a look');
    const budgets = out.indexOf('budgets need a look');
    expect(look).toBeLessThan(budgets);
    expect(budgets).toBeLessThan(out.indexOf('See debts'));
  });
});
