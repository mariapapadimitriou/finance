import { describe, expect, it } from 'vitest';
import { allocatePicks } from './SortCard.jsx';

// One payback, several purchases (2026-10-28).
const gym = (n, left = 50) => ({ id: `g${n}`, merchant: 'GoodLife Fitness', amount: 50, left });

describe('allocatePicks', () => {
  it('takes what is unpaid on each purchase, in the order picked', () => {
    const a = allocatePicks(150, [gym(1), gym(2), gym(3)]);
    expect(a.rows.map((r) => r.use)).toEqual([50, 50, 50]);
    expect(a.used).toBe(150);
    expect(a.left).toBe(0);
  });

  it('gives the last one only what is left of the money', () => {
    const a = allocatePicks(120, [gym(1), gym(2), gym(3)]);
    expect(a.rows.map((r) => r.use)).toEqual([50, 50, 20]);
    expect(a.left).toBe(0);
  });

  it('leaves the rest as money in when fewer are picked', () => {
    const a = allocatePicks(150, [gym(1)]);
    expect(a.used).toBe(50);
    expect(a.left).toBe(100);
  });

  it('counts only what is still unpaid on a purchase partly paid back', () => {
    const a = allocatePicks(80, [gym(1, 30), gym(2)]);
    expect(a.rows.map((r) => r.use)).toEqual([30, 50]);
    expect(a.left).toBe(0);
  });

  it('works in cents, so $0.10 + $0.20 is exactly $0.30', () => {
    const a = allocatePicks(0.3, [{ id: 'a', amount: 0.1 }, { id: 'b', amount: 0.2 }]);
    expect(a.used).toBe(0.3);
    expect(a.left).toBe(0);
  });
});
