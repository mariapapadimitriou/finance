import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import WhatWasThis, { CaseNeeds, TagEditor, bodyFor, effectWords, groupedCases, ready, startCase } from './WhatWasThis.jsx';
import { BatchMarkPanel, BATCH_CASES } from './BatchPanels.jsx';
import { COUNTS, VIEWS, accountOptionsFrom, amountRange, groupLabel, monthName, owedWords } from './TransactionsList.jsx';
import { SelectedBar } from './KeyboardReview.jsx';
import { CategoriesSection, NamesSection, TagsSection } from './RulesPanel.jsx';
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
  id: 'x', direction: 'out', current: 'spending', best: 'spending',
  groups: [{ key: 'spending', label: 'Spending' }, { key: 'not_spending', label: 'Not spending' },
           { key: 'not_mine', label: 'Not mine to count' }],
  cases: [
    { key: 'spending', label: 'A purchase', group: 'spending', needs: 'category',
      effect: 'Counts as spending in a category you pick.',
      remember: 'merchant', remember_label: 'Do this for every Pilot from now on' },
    { key: 'saved', label: 'Put into savings', group: 'not_spending', needs: 'account',
      effect: 'Moved to one of your savings accounts.', remember: 'destination',
      remember_label: 'Do this for every transfer to ••3333 from now on' },
    { key: 'shared', label: 'Paid for a group', group: 'spending', needs: 'split', effect: 'Only your share counts.', remember: null },
    { key: 'work', label: 'A work expense, to be reimbursed', group: 'not_mine', needs: null,
      effect: 'Left out of your spending until the money comes back.', remember: null },
  ],
  accounts: [{ id: 'inv1', label: 'My RRSP', kind: 'investment', source: 'linked', anchor: false, sub: 'Investment' },
             { id: 'hand:1', label: 'Wealthsimple TFSA', kind: 'investment', source: 'hand', anchor: false,
               sub: 'Investment · added by hand' },
             { id: 'sav', label: 'TD Savings', kind: 'savings', source: 'linked', anchor: true, sub: 'Part of your Anchor' }],
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

  it('step 1 (WW-02): the transaction, Pearl’s best guess on top, then the cases in their groups', () => {
    const out = html(<WhatWasThis tx={{ id: 'x', merchant: 'Pilot', amount: 500, inflow: false, date: '2026-10-07',
                                        account: 'TD Chequing ••4417' }}
                                  categories={CATS} initial={OUT} />);
    calm(out);
    for (const s of ['Pilot', 'Wednesday, October 7 · TD Chequing ••4417', '-$500.00', 'Pearl’s best guess',
      'A purchase', 'Counts as spending in a category you pick.', 'Spending', 'Not spending',
      'Not mine to count', 'Put into savings', 'A work expense, to be reimbursed']) {
      expect(out).toContain(s);
    }
    expect(out).not.toContain('What was it for?');              // that's step 2
    const groups = groupedCases(OUT);
    expect(groups.map((g) => g.label)).toEqual(['Pearl’s best guess', 'Spending', 'Not spending', 'Not mine to count']);
    expect(groups[0].cases.map((c) => c.key)).toEqual(['spending']);
    expect(groups[1].cases.map((c) => c.key)).toEqual(['shared']);   // the best guess isn't repeated
  });

  it('step 2 (WW-03): which savings account, with what each is, and what this does', () => {
    const saved = OUT.cases[1];
    const out = html(<CaseNeeds c={saved} data={OUT} s={{ account: 'sav' }} set={() => {}} spending={[]} />);
    for (const s of ['Which account did it go to?', '>My RRSP<', '>Wealthsimple TFSA<', '>TD Savings<',
      'Part of your Anchor', 'Investment · added by hand', 'Somewhere Pearl can’t see', 'Still counts as put away']) {
      expect(out).toContain(s);
    }
    expect(effectWords(saved, { account: 'sav' }, OUT, 'Safe to spend goes up by $200.00.', { amount: 200 }))
      .toBe('Safe to spend goes up by $200.00. It shows as “Put away to TD Savings” and adds $200.00 to Savings this month and to your Anchor.');
    expect(effectWords(saved, {}, OUT, '', { amount: 200 }))
      .toBe('It shows as “Put away” and adds $200.00 to Savings this month.');
    const refund = { key: 'refund', needs: 'refund', effect: 'Links to the purchase.',
                     candidates: [{ id: 'c1', merchant: 'Aritzia', date: '2026-09-26', amount: 148, category: 'Shopping', exact: true }] };
    expect(effectWords(refund, { charge: 'c1' }, OUT, '', { amount: 148 }))
      .toBe('The refund comes off Shopping in September. It isn’t income.');
  });

  it('points to Profile › Accounts when there is no savings account yet', () => {
    const out = html(<CaseNeeds c={OUT.cases[1]} data={{ ...OUT, accounts: [] }} s={{}} set={() => {}} spending={[]} />);
    expect(out).toContain('Add a savings or investment account on Profile › Accounts');
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
  it('offers the same list as the sort card, less the cases that need something per row', () => {
    expect(BATCH_CASES.map((c) => c.key)).toEqual(['spending', 'bill', 'moved', 'saved', 'lent', 'paying_back', 'work', 'not_mine']);
    const out = html(<BatchMarkPanel ids={['a', 'b', 'c']} categories={CATS} onDone={() => {}} onClose={() => {}} />);
    calm(out);
    expect(out).toContain('What were these?');
    expect(out).toContain('The same answer for all 3. Nothing becomes a rule.');
    expect(out).toContain('A work expense, to be reimbursed');   // the server's words, as everywhere
    expect(out).toContain('nl-pill nl-undo');
    expect(out).not.toContain('>Mark 3<');                         // tapping the last answer saves
  });

  it('the selected bar (VF-03) has the total, Change category, Mark as…, Tag, Leave out and Confirm', () => {
    const out = html(<SelectedBar count={3} total="-$148.95" onChange={() => {}} onConfirm={() => {}} onClear={() => {}}
                                  onMark={() => {}} onTag={() => {}} onLeaveOut={() => {}} />);
    expect(out).toContain('3 selected · -$148.95');
    for (const w of ['Change category', 'Mark as…', 'Tag', 'Leave out', 'Confirm', 'aria-label="Clear selection"']) {
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
    expect(COUNTS.map((c) => c.value)).toEqual(['', 'spending', 'income', 'none']);
    expect(VIEWS.map((v) => v.label)).toEqual(['By day', 'By merchant', 'By category']);
    expect(monthName('all')).toBe('All months');
    expect(monthName('last3')).toBe('Last 3 months');
    expect(owedWords({ names: ['Priya'], total: 194.2, count: 2 })).toBe('Priya owes you $194.20 for 2 purchases.');
    expect(owedWords({ names: ['Priya', 'Sam'], total: 50, count: 1 })).toBe('Priya and Sam owe you $50.00 for 1 purchase.');
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

  it('by merchant (VF-01): a header per group with its count and total', () => {
    expect(groupLabel({ name: 'Uber Eats', count: 3, spent: 74.3, income: 0, not_counted: 0 }))
      .toBe('UBER EATS · 3 PURCHASES · -$74.30');
    expect(groupLabel({ name: 'Northwind', count: 1, spent: 0, income: 2000, not_counted: 0 }))
      .toBe('NORTHWIND · 1 · +$2,000.00');
    expect(groupLabel({ name: 'TD Visa Payment', count: 1, spent: 0, income: 0, not_counted: 612 }))
      .toBe('TD VISA PAYMENT · 1 · $612.00');
  });
});

describe('rows and chips', () => {
  it('a chip a rule decided says so to a screen reader, with no lock and no icon (2026-10-22)', () => {
    const out = html(<CategoryChip label="Coffee" ruled />);
    expect(out).toContain('pk-cat ruled');
    expect(out).not.toContain('<svg');
    expect(out).toContain('aria-label="Coffee, from your rule"');
    expect(html(<CategoryChip label="Coffee" suggested ruled />)).toContain('suggested by Pearl');
  });

  it('a row shows its tags beside the category', () => {
    const out = html(<TxRow name="Flights" chip={{ label: 'Travel' }} amount={900} tags={['Ibiza']} onOpen={() => {}} />);
    expect(out).toContain('pk-tag');
    expect(out).toContain('>Ibiza<');
  });
});

describe('Categories and rules (CR-01 to CR-03)', () => {
  it('lists her merchant names, her tags, and each category with what Pearl decides', () => {
    const names = html(<NamesSection names={[{ key: 'roasted nut', merchant: 'Roasted Nut', name: 'The Nut' }]}
                                     onRename={() => {}} onForget={() => {}} />);
    expect(names).toContain('The Nut');
    expect(names).toContain('From your bank: Roasted Nut');
    expect(names).toContain('>Rename<');
    const tags = html(<TagsSection tags={[{ tag: 'Ibiza', count: 2, spent: 940 }]} onRename={() => {}} onRemove={() => {}} />);
    expect(tags).toContain('Ibiza');
    expect(tags).toContain('2 transactions · $940.00');
    expect(tags).toContain('>Remove<');
    const cats = html(<CategoriesSection categories={CATS} hidden={['Pets']} kinds={{ Dining: 'variable' }}
                                         pearl={{ Groceries: 'variable', Dining: 'fixed' }}
                                         onKind={() => {}} onHide={() => {}} />);
    expect(cats).toContain('Pearl decides · Variable');
    expect(cats).toContain('Always Variable');
    expect(cats).toContain('>Hidden<');
    expect(cats).toContain('>Show<');
    expect(cats).toContain('>Hide<');
    expect(cats).toContain('Essentials');
  });
});
