import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import WhatWasThis, { TagEditor, bodyFor, ready, startCase } from './WhatWasThis.jsx';
import { BatchMarkPanel, BATCH_CASES } from './BatchPanels.jsx';
import { FoldedList, AMOUNTS, COUNTS, VIEWS, accountOptionsFrom, amountRange, monthName } from './TransactionsList.jsx';
import { SelectedBar } from './KeyboardReview.jsx';
import { HiddenSection, NamesSection, TagsSection } from './RulesPanel.jsx';
import { CategoryChip, TxRow } from '../pearl/kit.jsx';

const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null/);
};

const CATS = [
  { name: 'Groceries', group: 'essentials' }, { name: 'Dining', group: 'lifestyle' },
  { name: 'Pets', group: 'essentials', hidden: true }, { name: 'Saved', group: 'savings' },
];

const OUT = {
  id: 'x', direction: 'out', current: 'spending',
  cases: [
    { key: 'spending', label: 'A purchase', needs: 'category', effect: 'Counts as spending, in the category you pick.',
      remember: 'merchant', remember_label: 'Do this for every Pilot from now on' },
    { key: 'saved', label: 'Put into savings or investments', needs: 'account',
      effect: 'Adds to what you put away. Not spending.', remember: 'destination',
      remember_label: 'Do this for every transfer to ••3333 from now on' },
    { key: 'shared', label: 'Paid for a group', needs: 'split', effect: 'Only your share counts.', remember: null },
    { key: 'work', label: 'A work expense I’ll be reimbursed for', needs: null,
      effect: 'Left out until the reimbursement arrives; then both disappear.', remember: null },
  ],
  accounts: [{ id: 'inv1', label: 'My RRSP', kind: 'investment', source: 'linked' },
             { id: 'hand:1', label: 'Wealthsimple TFSA', kind: 'investment', source: 'hand' }],
  saved_to: null, income_kinds: { salary: 'Salary' }, income_kind: null, joint: '', joint_people: [],
  tags: [], categories: ['Groceries', 'Dining'],
};

describe('What was this? (2026-10-14)', () => {
  it('starts on the row’s current case', () => {
    expect(startCase(OUT)).toBe('spending');
    expect(startCase({ ...OUT, current: 'nope' })).toBe('');
    expect(startCase(null)).toBe('');
  });

  it('knows when a choice is complete, and what to send', () => {
    const [spending, saved, shared, work] = OUT.cases;
    expect(ready(spending, {})).toBe(false);
    expect(ready(spending, { category: 'Groceries' })).toBe(true);
    expect(bodyFor(spending, { category: 'Groceries', remember: true }))
      .toEqual({ case: 'spending', category: 'Groceries', remember: true });
    expect(ready(saved, {})).toBe(true);                       // the account is optional
    expect(bodyFor(saved, { account: 'inv1' })).toEqual({ case: 'saved', account: 'inv1', remember: false });
    expect(ready(shared, {})).toBe(true);
    expect(bodyFor(work, {})).toEqual({ case: 'work' });
    const refund = { key: 'refund', needs: 'refund' };
    expect(ready(refund, {})).toBe(false);
    expect(bodyFor(refund, { charge: 'c1' })).toEqual({ case: 'refund', charge: 'c1' });
    expect(bodyFor(refund, { category: 'Dining', other: true })).toEqual({ case: 'refund', category: 'Dining' });
    const back = { key: 'paying_back', needs: 'borrowed' };
    expect(ready(back, {})).toBe(true);
    expect(ready(back, { counted: false })).toBe(false);
    expect(bodyFor(back, { counted: false, category: 'Dining' }))
      .toEqual({ case: 'paying_back', category: 'Dining', counted: false });
    const pay = { key: 'pay', needs: 'income_kind' };
    expect(bodyFor(pay, { income_kind: 'salary' })).toEqual({ case: 'pay', income_kind: 'salary' });
    const payback = { key: 'payback', needs: 'candidates' };
    expect(bodyFor(payback, { charge: 'c1', person: 'Priya' }))
      .toEqual({ case: 'payback', charge: 'c1', person: 'Priya' });
  });

  it('draws every case with what it does, and the chosen one’s needs', () => {
    const out = html(<WhatWasThis tx={{ id: 'x', merchant: 'Pilot', amount: 500, inflow: false }}
                                  categories={CATS} initial={OUT} showHead />);
    calm(out);
    expect(out).toContain('A purchase · now');
    expect(out).toContain('Put into savings or investments');
    expect(out).toContain('Adds to what you put away. Not spending.');
    expect(out).toContain('What was it for?');                  // the current case opened
    expect(out).toContain('>Groceries<');
    expect(out).not.toContain('>Pets<');                         // hidden stays out
    expect(out).toContain('Do this for every Pilot from now on');
    expect(out).toContain('A rule you can see and undo in Categories and rules.');
    expect(out).toContain('Pilot');
    expect(out).toContain('-$500.00');
  });

  it('offers the savings accounts, linked and added by hand, when Saved is chosen', () => {
    const out = html(<WhatWasThis tx={{ id: 'x', merchant: 'TFR', amount: 500, inflow: false }}
                                  categories={CATS} initial={{ ...OUT, current: 'saved' }} />);
    expect(out).toContain('Which account did it go to?');
    expect(out).toContain('>My RRSP<');
    expect(out).toContain('>Wealthsimple TFSA<');
    expect(out).toContain('Added by you');
    expect(out).toContain('Not sure');
    expect(out).toContain('Do this for every transfer to ••3333 from now on');
  });

  it('points to Profile › Accounts when there is no savings account yet', () => {
    const out = html(<WhatWasThis tx={{ id: 'x', merchant: 'TFR', amount: 500, inflow: false }}
                                  categories={CATS} initial={{ ...OUT, current: 'saved', accounts: [] }} />);
    expect(out).toContain('Add one on Profile › Accounts');
  });

  it('a tag editor lists the tags with a way to take each off', () => {
    const out = html(<TagEditor tags={['Ibiza', 'Work']} known={['Ibiza', 'Reno']} onChange={() => {}} />);
    expect(out).toContain('>Ibiza<');
    expect(out).toContain('aria-label="Remove Work"');
    expect(out).toContain('>Reno<');                            // a known tag, offered
    expect(out).toContain('Add a tag, like Ibiza');
  });
});

describe('the selection, answered at once', () => {
  it('offers the cases that need nothing per row', () => {
    expect(BATCH_CASES.map((c) => c.key)).toEqual(['spending', 'moved', 'saved', 'lent', 'work', 'not_mine']);
    const out = html(<BatchMarkPanel ids={['a', 'b', 'c']} categories={CATS} onDone={() => {}} onClose={() => {}} />);
    calm(out);
    expect(out).toContain('What were these?');
    expect(out).toContain('The same answer for all 3. Nothing becomes a rule.');
    expect(out).toContain('Work expenses I’ll be reimbursed for');
    expect(out).toContain('>Mark 3<');
  });

  it('the selected bar has Mark as, Tag and Leave out beside the keys', () => {
    const out = html(<SelectedBar count={4} onChange={() => {}} onConfirm={() => {}} onClear={() => {}}
                                  onMark={() => {}} onTag={() => {}} onLeaveOut={() => {}} />);
    expect(out).toContain('4 selected');
    for (const w of ['Change category', 'Mark as…', 'Tag', 'Leave out', 'Confirm suggestions', 'Clear']) {
      expect(out).toContain(w);
    }
    // On a phone (no single keys) the key caps go.
    const phone = html(<SelectedBar count={1} singleKey={false} onChange={() => {}} onConfirm={() => {}} onClear={() => {}} />);
    expect(phone).not.toContain('kr-key');
  });
});

describe('the list’s filters and views', () => {
  it('amount ranges become min and max', () => {
    expect(amountRange('')).toEqual({});
    expect(amountRange('0-20')).toEqual({ amount_min: '0', amount_max: '20' });
    expect(amountRange('500-')).toEqual({ amount_min: '500' });
    expect(AMOUNTS.map((a) => a.label)).toContain('Over $500');
    expect(COUNTS.map((c) => c.value)).toEqual(['', 'spending', 'income', 'none']);
    expect(VIEWS.map((v) => v.label)).toEqual(['By day', 'By merchant', 'By category']);
    expect(monthName('all')).toBe('All months');
  });

  it('the account filter lists the accounts as Profile › Accounts does', () => {
    const overview = {
      linked: [
        { id: 'a', name: 'My Visa', nickname: 'My Visa', mask: '1203', institution: 'TD', source: 'plaid', kind: 'card', transactions: 40 },
        { id: 'b', name: 'Chequing', mask: '4411', institution: 'TD', source: 'plaid', kind: 'chequing', transactions: 80, joint: true },
        { id: 'c', name: 'Chequing', mask: '9001', institution: 'RBC', source: 'plaid', kind: 'chequing', transactions: 10 },
        { id: 'inv', name: 'RRSP', mask: '4444', institution: 'TD', source: 'plaid', kind: 'investment', transactions: 0 },
        { id: 'gone', name: 'Old card', mask: '', institution: 'TD', source: 'plaid', kind: 'card', transactions: 0 },
      ],
      added: [
        { id: 's', name: 'Amex statement', mask: '', institution: '', source: 'statement', kind: 'card', transactions: 12 },
        { id: 'hand:1', name: 'Meridian Savings', mask: '3333', institution: '', source: 'hand', kind: 'savings', transactions: 0 },
      ],
    };
    const opts = accountOptionsFrom(overview, []);
    expect(opts[0]).toEqual({ value: '', label: 'All accounts' });
    expect(opts[1].group).toBe('Linked');
    expect(opts[1].options.map((o) => o.label)).toEqual(['My Visa ••1203', 'TD Chequing ••4411 · Joint', 'RBC Chequing ••9001']);
    expect(opts[2].group).toBe('Added by you');
    expect(opts[2].options.map((o) => o.label)).toEqual(['Amex statement']);
    // Until the overview arrives, the ledger's own names.
    expect(accountOptionsFrom(null, [{ account_id: 'q', account_name: 'Card', institution: '' }])[1])
      .toEqual({ value: 'q', label: 'Card' });
  });

  it('folded by merchant: one line each, biggest first, with what else came in', () => {
    const rows = [
      { merchant: 'Loblaws', logo: '', count: 3, spent: 180.5, income: 0, not_counted: 0 },
      { merchant: 'Northwind', logo: '', count: 1, spent: 0, income: 2000, not_counted: 0 },
      { merchant: 'TD Visa Payment', logo: '', count: 1, spent: 0, income: 0, not_counted: 300 },
    ];
    const out = html(<FoldedList rows={rows} kind="merchant" onPick={() => {}} />);
    calm(out);
    expect(out).toContain('3 transactions');
    expect(out).toContain('-$180.50');
    expect(out).toContain('+$2,000.00');
    expect(out).toMatch(/pk-amt muted[^>]*>\$300\.00/);
  });
});

describe('rows and chips', () => {
  it('a chip a rule decided wears a lock and says so', () => {
    const out = html(<CategoryChip label="Coffee" ruled />);
    expect(out).toContain('pk-cat ruled');
    expect(out).toContain('aria-label="Coffee, from your rule"');
    expect(html(<CategoryChip label="Coffee" suggested ruled />)).toContain('suggested by Pearl');
  });

  it('a row shows its tags beside the category', () => {
    const out = html(<TxRow name="Flights" chip={{ label: 'Travel' }} amount={900} tags={['Ibiza']} onOpen={() => {}} />);
    expect(out).toContain('pk-tag');
    expect(out).toContain('>Ibiza<');
  });
});

describe('Categories and rules: names, tags, hidden', () => {
  it('lists her merchant names, her tags, and which categories she uses', () => {
    const names = html(<NamesSection names={[{ key: 'roasted nut', merchant: 'Roasted Nut', name: 'The Nut' }]} onForget={() => {}} />);
    expect(names).toContain('The Nut');
    expect(names).toContain('Use the bank’s name');
    const tags = html(<TagsSection tags={[{ tag: 'Ibiza', count: 2, spent: 940 }]} onRename={() => {}} onRemove={() => {}} />);
    expect(tags).toContain('Ibiza');
    expect(tags).toContain('2 transactions');
    const hidden = html(<HiddenSection categories={CATS} hidden={['Pets']} onHide={() => {}} />);
    expect(hidden).toMatch(/<input type="checkbox" checked=""[^>]*\/>Groceries/);
    expect(hidden).toMatch(/<input type="checkbox"[^>]*\/>Pets/);
    expect(hidden).not.toMatch(/checked=""[^>]*\/>Pets/);
  });
});
