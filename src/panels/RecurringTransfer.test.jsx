import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Question, queue, questionLabel } from './NeedsALook.jsx';

const html = (el) => renderToStaticMarkup(el);
const rows = ['2026-10-01', '2026-09-01', '2026-08-01'].map((d, i) => ({
  id: `r${i}`, date: d, merchant: 'Send E-tfr R1', amount: 1500, account_name: 'chq' }));
const item = {
  key: 'rt:abc', txn: rows[0], rows, asked: ['r0', 'r1'],
  reason: '$1,500.00, every month, around the 1st: 3 times since August 1.',
  series: { key: 'rt:abc', amount: 1500, cadence: 'monthly', count: 3, when: 'every month, around the 1st' },
};

describe('Recurring transfers in Needs a look (2026-10-27)', () => {
  it('is one item in the queue for the whole series', () => {
    const q = queue({ recurring_transfer: [item], unsorted: { transfers: [], groups: [] } });
    expect(q.map((x) => [x.kind, x.key])).toEqual([['recurring', 'rt:abc']]);
    expect(questionLabel(q[0])).toBe('Recurring transfer?');
  });

  it('asks once, showing the transfers and what it found', () => {
    const page = html(<Question it={{ ...item, kind: 'recurring' }} commit={() => {}} act={() => {}} />);
    expect(page).toContain('Is this a recurring transfer?');
    expect(page).toContain('every month, around the 1st: 3 times since August 1.');
    expect(page).toContain('Oct 1');
    expect(page).toContain('Yes, it repeats');
    expect(page).toContain('No, they’re separate');
    expect(page).toContain('Skip for now');
  });
});
