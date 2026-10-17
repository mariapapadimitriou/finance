import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Card, Done, Picker, Progress, Prompt, effectWords, rulesWords } from './QuickSort.jsx';

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
    expect(out).toContain('You’ve got 6 new transactions to sort');
    expect(out).toContain('takes about a minute');
    expect(out).toContain('>Start<');
    expect(out).toContain('>Later<');
    expect(html(<Prompt count={1} onStart={noop} onLater={noop} />)).toContain('You’ve got 1 new transaction to sort');
  });

  it('the card shows the transaction, signed and coloured, and the progress', () => {
    const out = html(<Card item={item} />);
    expect(out).toContain('Shoppers Drug Mart');
    expect(out).toContain('Friday, October 9 · Visa ··1203');
    expect(out).toContain('-$18.47');
    expect(out).toContain('qs-amt out');
    const bar = html(<Progress n={6} at={1} />);
    expect(bar.match(/class="on"/g)).toHaveLength(2);
    expect(bar).toContain('aria-valuenow="2"');
  });

  it('the picker puts suggested and recent first, with the guess marked', () => {
    const out = html(<Picker item={item} categories={categories} onSave={noop} onNotPurchase={noop} />);
    expect(out.indexOf('Suggested')).toBeLessThan(out.indexOf('Recent'));
    expect(out).toContain('pk-opt guess');
    expect(out).toContain('Search categories');
    expect(out).toContain('It wasn’t a purchase…');
    expect(out).toContain('Opens “What was this?” for transfers, paybacks and refunds.');
    expect(out).toContain('Save and next');
    expect(out).toContain('disabled=""');
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
