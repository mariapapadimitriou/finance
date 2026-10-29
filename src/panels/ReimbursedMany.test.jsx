import { describe, expect, it } from 'vitest';
import { allocatePicks, steps } from './SortCard.jsx';

// Many to many (2026-10-29): deposits toward what an expense still needs.
describe('Several deposits for one expense', () => {
  it('each gives what is still needed, up to what it has left', () => {
    const a = allocatePicks(300, [{ id: 'd2', left: 100 }, { id: 'd1', left: 200 }]);
    expect(a.rows.map((r) => r.use)).toEqual([100, 200]);
    expect(a.left).toBe(0);
  });

  it('the step knows how much the expense still needs', () => {
    const out = { key: 'p:h', kind: 'panel', txn: { id: 'h', date: '2026-10-09', merchant: 'Marriott', amount: 300 } };
    const cases = { cases: [{ key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine',
      needs: 'reimbursed', owed: 300, candidates: [{ id: 'd1', merchant: 'Acme', date: '2026-10-21', amount: 200, left: 200 }] }] };
    expect(steps(out, cases, 'all').S.reimbursed.owed).toBe(300);
  });
});
