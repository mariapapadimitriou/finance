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
    expect(out).toContain('My own money: a transfer, not income');
    expect(out).toContain('Money into your joint account from outside Pearl.');
    expect(out).toContain('>Maya<');
    expect(out).toContain('Pays for Maya’s part of this month’s joint spending');
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

describe('Debts sits in Cash flow (THL-209, 2026-10-15)', () => {
  it('draws Cash flow’s pills, with Debts current', () => {
    const out = html(<DebtsPage data={{ debts: [], count: 0, total: 0, minimums: 0,
                                        missing_details: 0 }} onEdit={() => {}} />);
    expect(out).toContain('class="in-tabs"');
    expect(out).toMatch(/aria-current="page"[^>]*>Debts</);
    expect(out).toContain('>Cash flow</h1>');
    expect(out).toMatch(/class="in-tab">Transactions</);
  });
});

describe('who a joint account is shared with (2026-10-14)', () => {
  it('names them, and the account says so', async () => {
    const { parsePeople, peopleWords, accountMeta, PeopleDialog } = await import('./AccountsPanel.jsx');
    expect(parsePeople('Sam, alex; Sam and Jo')).toEqual(['Sam', 'alex', 'Jo']);
    expect(peopleWords(['Sam'])).toBe('Sam');
    expect(peopleWords(['Sam', 'Alex', 'Jo'])).toBe('Sam, Alex and Jo');
    const a = { name: 'Family chequing', kind: 'chequing', source: 'plaid', status: 'joint',
                joint: true, joint_share: 50, joint_people: ['Sam', 'Alex'], balance: 900,
                updated_at: null };
    expect(accountMeta(a)).toContain('joint with Sam and Alex, your share is 50%');
    const dialog = renderToStaticMarkup(<PeopleDialog a={a} onClose={() => {}} onSave={() => {}} />);
    expect(dialog).toContain('Who do you share it with?');
    expect(dialog).toContain('value="Sam, Alex"');
  });

  it('“Who put this in?” offers me and each of them', async () => {
    const { depositChoices } = await import('./joint.js');
    expect(depositChoices(['Sam', 'Alex'], 'Sam and Alex').map((c) => [c.label, c.who, c.person]))
      .toEqual([['Me', 'me', null], ['Sam', 'them', 'Sam'], ['Alex', 'them', 'Alex']]);
    // Before she names anyone: the account's label, as before.
    expect(depositChoices([], 'Family').map((c) => c.label)).toEqual(['Me', 'Family']);
    const { JointIn } = await import('./NeedsALook.jsx');
    const out = renderToStaticMarkup(
      <JointIn it={{ txn: { id: 't', merchant: 'Sister', date: '2026-10-02', amount: -60 },
                     label: 'Sam and Alex', people: ['Sam', 'Alex'] }} act={() => {}} />);
    for (const s of ['Who put this in?', '>Me<', '>Sam<', '>Alex<']) expect(out).toContain(s);
  });

  it('Transfers is called Transfers', async () => {
    const { categoryLabel } = await import('./CategoryPicker.jsx');
    expect(categoryLabel('Transfers')).toBe('Transfers');
  });
});
