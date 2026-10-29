import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IncomeBillsPage } from './IncomeBillsPanel.jsx';

// After Start over (2026-10-29): what Pearl finds again is a suggestion until she confirms it.
const base = {
  today: '2026-10-29', pays: [], expected: { amount: null, varies: false, estimate: null, months: [] },
  rent_question: null,
  candidates: [{ payer: 'Acme Corp', name: 'Acme Corp', amount: 2300, cadence: 'biweekly', last: '2026-10-27' }],
  bills: [{ key: 'b1', name: 'Netflix', amount: 17.99, cadence: 'monthly', day: 20, ticked: true, counts: null, source: 'found' },
          { key: 'b2', name: 'Rogers', amount: 85, cadence: 'monthly', day: 24, ticked: true, counts: null, source: 'found' }],
  totals: { income: null, bills: 102.99 },
};
const text = (data) => renderToStaticMarkup(<IncomeBillsPage data={data} onOpen={() => {}} />)
  .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

describe('Income and bills, found but not confirmed', () => {
  it('says the bills and the pay are what Pearl found', () => {
    const t = text({ ...base, checked: { income: null, bills: null } });
    expect(t).toContain('Regular bills Pearl found');
    expect(t).toContain('Found in your transactions, not confirmed yet.');
    expect(t).toContain('Confirm 2');
    expect(t).toContain('Is Acme Corp your pay?');
    expect(t).not.toContain('No income confirmed yet');
  });

  it('once confirmed, they are just her bills', () => {
    const t = text({ ...base, candidates: [], checked: { income: '2026-10-29', bills: '2026-10-29' } });
    expect(t).toContain('Regular bills');
    expect(t).not.toContain('Pearl found');
    expect(t).not.toContain('not confirmed yet');
  });
});
