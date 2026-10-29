import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AddTransaction } from './TransactionDetail.jsx';

const cats = [
  { name: 'Groceries', group: 'essentials' }, { name: 'Dining', group: 'lifestyle' },
  { name: 'Income', group: 'income' }, { name: 'Transfers', group: 'transfer' },
  { name: 'Lent', group: 'transfer' }, { name: 'Unsorted transfers', group: 'transfer' },
];

describe('Add a transaction (2026-10-28)', () => {
  const html = renderToStaticMarkup(<AddTransaction categories={cats} onClose={() => {}} onSaved={() => {}} />);
  const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

  it('picks a category from the spending tiles, not a dropdown of everything', () => {
    expect(html).not.toContain('<select');
    expect(text).toContain('Groceries');
    expect(text).toContain('Dining');
    for (const no of ['Income', 'Transfers', 'Lent', 'Unsorted transfers']) expect(text).not.toContain(` ${no} `);
    expect(text).toContain('Pick one, or leave it and Pearl suggests one.');
  });

  it('puts Amount and Date side by side, the amount with its dollar sign', () => {
    expect(html).toContain('class="txd-pair"');
    expect(html).toContain('class="txd-money"');
    expect(html).toContain('placeholder="0.00"');
  });

  it('keeps Add it in reach at the bottom', () => {
    expect(html).toMatch(/class="txd-sticky"[^]*Add it/);
  });
});
