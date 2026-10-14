import { describe, expect, it } from 'vitest';
import { KIND_LABELS, chips, inView, queue } from './NeedsALook.jsx';

// THL-213: Needs a look's Skipped bucket and the filter chips.

const txn = (id, date) => ({ id, date, merchant: id, amount: 20 });
const data = {
  count: 3, skipped: 2,
  unsorted: { groups: [], transfers: [{ ...txn('t1', '2026-10-01'), skipped: true },
                                       txn('t2', '2026-10-02')] },
  unsure_category: [{ key: 'c:1', txn: txn('c1', '2026-10-03'), guess: 'Groceries', skipped: false },
                    { key: 'c:2', txn: txn('c2', '2026-10-04'), guess: 'Other', skipped: true }],
  duplicate: [{ key: 'd:1', txn: txn('d1', '2026-10-05'), skipped: false }],
};

describe('Needs a look chips', () => {
  const items = queue(data);

  it('carries skipped from the server, transfers included', () => {
    expect(items.filter((i) => i.skipped).map((i) => i.key)).toEqual(['u:t1', 'c:2']);
  });

  it('shows All, each type with open questions, then Skipped', () => {
    expect(chips(items).map((c) => `${c.label} (${c.count})`)).toEqual(
      ['All (3)', 'Where it went (1)', 'Categories (1)', 'Duplicates (1)', 'Skipped (2)']);
    expect(Object.keys(KIND_LABELS)).toHaveLength(7);
  });

  it('leaves Skipped out when nothing is skipped', () => {
    const none = queue({ ...data, unsorted: { groups: [], transfers: [txn('t2', '2026-10-02')] },
                         unsure_category: [] });
    expect(chips(none).map((c) => c.key)).toEqual(['all', 'unsorted', 'duplicate']);
  });

  it('filters by type, keeping skipped ones apart', () => {
    expect(inView(items, 'all').map((i) => i.key)).toEqual(['u:t2', 'c:1', 'd:1']);
    expect(inView(items, 'category').map((i) => i.key)).toEqual(['c:1']);
    expect(inView(items, 'skipped').map((i) => i.key)).toEqual(['u:t1', 'c:2']);
  });
});
