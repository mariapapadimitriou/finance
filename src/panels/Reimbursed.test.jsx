import { describe, expect, it } from 'vitest';
import { steps } from './SortCard.jsx';

// Reimbursements both ways (2026-10-29).
const out = { key: 'cat:a', kind: 'category', txn: { id: 'a', date: '2026-10-09', merchant: 'Uber', amount: 45 } };
const inn = { key: 'in:p', kind: 'money_in', txn: { id: 'p', date: '2026-10-26', merchant: 'Acme Corp Expenses', amount: -160 } };

describe('A work expense already reimbursed', () => {
  it('asks "Has it been reimbursed yet?" with the deposits that came', () => {
    const cases = { cases: [{ key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine',
      needs: 'reimbursed', candidates: [{ id: 'p', merchant: 'Acme Corp Expenses', date: '2026-10-26', amount: 160, left: 160 }] }] };
    const { S } = steps(out, cases, 'all');
    expect(S.reimbursed.title).toBe('Has it been reimbursed yet?');
    expect(S.reimbursed.ask).toBe('deposit');
    expect(S.reimbursed.candidates).toHaveLength(1);
  });

  it('with no deposit yet, there is no such step', () => {
    const cases = { cases: [{ key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine', needs: null }] };
    expect(steps(out, cases, 'all').S.reimbursed).toBeUndefined();
  });
});

describe('One deposit, several expenses', () => {
  it('the reimbursement picker is the same pick step a payback has', () => {
    const cases = { cases: [{ key: 'reimbursement', label: 'A reimbursement', group: 'not_income', needs: 'candidates',
      candidates: [{ id: 'a', merchant: 'Uber', amount: 45, left: 45 }, { id: 'b', merchant: 'Marriott', amount: 115, left: 115 }] }] };
    const { S } = steps(inn, cases);
    expect(S.pick_reimbursement.ask).toBe('pick');
    expect(S.pick_reimbursement.key).toBe('reimbursement');
    expect(S.pick_reimbursement.candidates.map((c) => c.left)).toEqual([45, 115]);
  });
});
