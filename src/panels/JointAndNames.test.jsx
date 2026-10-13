import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { JointIn } from './NeedsALook.jsx';
import { partyTitle } from './TransactionDetail.jsx';
import { DebtsPage } from './DebtsPanel.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('money into a joint account', () => {
  const it_ = {
    key: 'joint:x', kind: 'joint_in', label: 'Maya',
    txn: { id: 'x', date: '2026-10-05', merchant: 'Maya Papas', amount: -200,
           account_name: 'Joint Chequing' },
  };

  it('asks who put it in: me, or the other person', () => {
    const out = html(<JointIn it={it_} busy={false} onSkip={() => {}} act={() => {}} />);
    expect(out).toContain('Who put this in?');
    expect(out).toContain('From an account of mine that isn’t in Pearl. It isn’t income.');
    expect(out).toContain('>Maya<');
    expect(out).toContain('It pays for that much of this month’s joint spending');
    expect(out).toContain('The same for every deposit from Maya Papas');
  });
});

describe('who an e-Transfer was from or to', () => {
  it('asks when the bank didn’t say, and offers a change when it did', () => {
    expect(partyTitle({ direction: 'from', name: null })).toBe('Who sent this?');
    expect(partyTitle({ direction: 'to', name: null })).toBe('Who was it to?');
    expect(partyTitle({ direction: 'from', name: 'Priya' })).toBe('Change who it was from');
  });
});

describe('Debts sits with the other Growth pages', () => {
  it('draws the same Growth tabs, with Debts current', () => {
    const out = html(<DebtsPage data={{ debts: [], count: 0, total: 0, minimums: 0,
                                        missing_details: 0 }} onEdit={() => {}} />);
    expect(out).toContain('class="in-tabs"');
    expect(out).toMatch(/aria-current="page"[^>]*>Debts</);
    expect(out).toContain('>Growth</h1>');
  });
});
