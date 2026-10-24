import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import QuickSort, { Done, Progress, Prompt, asItem, effectWords, rulesWords } from './QuickSort.jsx';
import SortCard from './SortCard.jsx';

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};

const item = { id: 't1', merchant: 'Shoppers Drug Mart', date: '2026-10-09', account: 'Visa ··1203',
               amount: 18.47, inflow: false, guess: 'Personal Care', suggested: ['Personal Care', 'Health'],
               recent: ['Dining', 'Coffee', 'Transport'] };
const categories = [
  { name: 'Groceries', group: 'essentials' }, { name: 'Shopping', group: 'lifestyle' },
  { name: 'Personal Care', group: 'lifestyle' }, { name: 'Health', group: 'essentials' },
  { name: 'Dining', group: 'lifestyle' }, { name: 'Coffee', group: 'lifestyle' }, { name: 'Transport', group: 'essentials' },
];

describe('Quick sort (QS-01 to QS-04)', () => {
  it('the prompt says how many and offers Start and Later', () => {
    const out = html(<Prompt count={6} onStart={noop} onLater={noop} />);
    expect(out).toContain('Welcome back');
    expect(out).toContain('6 transactions need a look');
    expect(out).toContain('takes about 2 minutes');
    expect(out).toContain('>Start<');
    expect(out).toContain('>Later<');
    expect(html(<Prompt count={1} onStart={noop} onLater={noop} />)).toContain('1 transaction needs a look');
  });

  it('counts what Needs a look counts: every kind of question (2026-10-24)', () => {
    const review = {
      count: 3, unsorted: { transfers: [{ id: 'u1', date: '2026-10-05', merchant: 'Internet Transfer To', amount: 120 }], groups: [] },
      unsure_category: [{ key: 'cat:m1', txn: { id: 'm1', date: '2026-10-09', merchant: 'Mystery Shop', amount: 40 }, guess: 'Other' }],
      joint_in: [{ key: 'joint:j1', txn: { id: 'j1', date: '2026-10-04', merchant: 'Tfr-fr', amount: -300 } }],
    };
    const out = html(<QuickSort data={{ count: 3, keys: ['u:u1', 'cat:m1', 'joint:j1'], review }} categories={categories} />);
    expect(out).toContain('3 transactions need a look');
  });

  it('the card is the sort card: the transaction, "Is this Personal Care?" and the progress', () => {
    const out = html(<SortCard it={asItem(item)} categories={categories} commit={noop} onSkip={noop} />);
    expect(out).toContain('Shoppers Drug Mart');
    expect(out).toContain('Friday, October 9 · from Visa ··1203');
    expect(out).toContain('-$18.47');
    expect(out).toContain('Is this Personal Care?');
    for (const a of ['Yes, Personal Care', 'No, a different category', 'It wasn’t a purchase']) expect(out).toContain(a);
    expect(out).toContain('Skip for now');
    expect(out).not.toContain('Save and next');
    const bar = html(<Progress n={6} at={1} />);
    expect(bar.match(/class="on"/g)).toHaveLength(2);
    expect(bar).toContain('aria-valuenow="2"');
  });

  it('"It wasn’t a purchase" leads to the same list Needs a look and the panel use', () => {
    const out = html(<SortCard it={asItem(item)} categories={categories} commit={noop}
                               initialPath={[{ step: 'q1', v: 'else' }]} />);
    expect(out).toContain('aria-label="Change: Not a purchase"');
    for (const a of ['A bill', 'My own money', 'A loan', 'Not mine']) expect(out).toContain(a);
    expect(out).toContain('nl-tiles');
  });

  it('the done screen shows Allowance before and after, the reason and the rules', () => {
    const r = { sorted: 6, skipped: 0, before: 642.18, after: 598.4,
                reason: 'Two were Groceries Pearl had counted as Shopping, and one transfer was Saved.', rules: 2 };
    const out = html(<Done r={r} onDone={noop} />);
    expect(out).toContain('All sorted');
    expect(out).toContain('6 sorted. Thanks!');
    expect(out).toContain('Allowance: $642.18 → $598.40');
    expect(out).toContain('2 rules saved, so these sort themselves next time.');
    expect(effectWords({ before: 10, after: 10 })).toBe('Allowance: $10.00, unchanged');
    expect(effectWords({ before: null, after: 20 })).toBe('Allowance: — → $20.00');
    expect(rulesWords(1)).toBe('1 rule saved, so it sorts itself next time.');
    expect(rulesWords(0)).toBe('');
    const none = html(<Done r={{ sorted: 0, skipped: 2, rules: 0 }} onDone={noop} />);
    expect(none).toContain('Nothing sorted this time');
    expect(none).toContain('still in Needs a look');
  });
});
