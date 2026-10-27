import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import SortCard, { paidPartOf, paybackEffect } from './SortCard.jsx';
import { LinkToSplit } from './Splits.jsx';

const html = (el) => renderToStaticMarkup(el);
const inn = { key: 'in:a', kind: 'money_in',
              txn: { id: 'a', date: '2026-10-05', merchant: 'e-Transfer from Anna', amount: -100, account_name: 'chq' } };
const cases = { cases: [{ key: 'payback', label: 'Someone paying me back', group: 'not_income', needs: 'candidates',
  candidates: [{ id: 'c', merchant: 'Sushi Nami', date: '2026-10-03', amount: 80, category: 'Dining' }] }] };

describe('Paid back, part of it (2026-10-26)', () => {
  it('is all of it unless she types less', () => {
    expect(paidPartOf('100.00', 100)).toBe(null);
    expect(paidPartOf('40', 100)).toBe(40);
    expect(paidPartOf('0', 100)).toBe(null);
    expect(paidPartOf('', 100)).toBe(null);
    expect(paidPartOf('150', 100)).toBe(null);
  });

  it('says the rest counts as money in', () => {
    expect(paybackEffect({ merchant: 'Sushi Nami', split: true }, '', '$40.00', '$60.00'))
      .toBe('$40.00 comes off what you spent at Sushi Nami. Not income. The other $60.00 counts as money in.');
  });

  it('the sort card asks how much, filled with the whole amount', () => {
    const page = html(<SortCard it={inn} cases={cases} commit={() => {}}
                                initialPath={[{ step: 'q1', v: 'else' }, { step: 'what_in', v: 'payback' }]} />);
    expect(page).toContain('How much of it was paying you back?');
    expect(page).toMatch(/value="100.00"/);
  });

  it('the panel asks too, once a split is picked', () => {
    const tx = { id: 'a', full_amount: 100, repayment: {
      suggestion: { charge_id: 'c', name: 'Anna' },
      splits: [{ charge_id: 'c', name: 'Anna', merchant: 'Sushi Nami', owes: 40, date: '2026-10-03' }] } };
    const page = html(<LinkToSplit tx={tx} onLink={() => {}} onNone={() => {}} />);
    expect(page).toContain('How much of it was paying you back?');
    expect(page).toMatch(/value="100.00"/);
  });
});
