import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SetupAgainList, SharedAccountsForm, shareable, sharedChanges } from './SetupAgain.jsx';
import { StartedOver } from './DataPanel.jsx';

const text = (el) => renderToStaticMarkup(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const cash = { id: 'cash', name: 'Cash', mask: '6922', institution: 'Wealthsimple', kind: 'chequing',
               source: 'plaid', joint: false, joint_people: [] };
const visa = { ...cash, id: 'visa', name: 'Aeroplan Visa', mask: '4145', institution: 'TD', kind: 'card' };
const shared = { ...cash, id: 'fam', name: 'Joint chequing', mask: '1111', joint: true, joint_people: ['Anastasia'] };
const rrsp = { ...cash, id: 'rrsp', name: 'RRSP', mask: '', kind: 'investment' };
const steps = [
  { key: 'shared', title: 'Which accounts do you share?', sub: 'Mark joint accounts so only your share counts.', done: false },
  { key: 'income', title: 'Confirm your income and bills', sub: 'Pearl found them again. Say which are right.', done: true },
  { key: 'accounts', title: 'Check how each account counts', sub: 'Nicknames, which count in your budget, and your Anchor.', done: false },
];

describe('Set up again, after Start over (2026-10-29)', () => {
  it('lists what only she can set again, and what is done', () => {
    const t = text(<SetupAgainList data={{ active: true, left: 2, steps }} onOpen={() => {}} onHide={() => {}} />);
    for (const s of ['Set Pearl up again', '2 things to set again', 'Which accounts do you share?',
      'Confirm your income and bills', 'Done', 'Check how each account counts', 'Hide this list']) {
      expect(t).toContain(s);
    }
  });

  it('shows on the starting-fresh page once the history is back', () => {
    const list = <SetupAgainList data={{ active: true, left: 2, steps }} onOpen={() => {}} heading="Set up again" />;
    expect(text(<StartedOver imported={1324} needsLook={12} setup={list} />)).toContain('Set up again');
    expect(text(<StartedOver syncing setup={list} />)).not.toContain('Set up again');
  });

  it('asks about bank accounts and cards, not investments', () => {
    expect(shareable([cash, visa, rrsp]).map((a) => a.id)).toEqual(['cash', 'visa']);
    const t = text(<SharedAccountsForm accounts={[cash, visa]} onSave={() => {}} onNone={() => {}} />);
    expect(t).toContain('Cash ••6922');
    expect(t).toContain('None of these are shared');
  });

  it('saves who each shared account is shared with, and unshares the rest', () => {
    expect(sharedChanges([cash, shared], { cash: { on: true, names: 'Anastasia, Sam' }, fam: { on: false, names: '' } }))
      .toEqual({ changes: [['cash', { joint_people: ['Anastasia', 'Sam'] }], ['fam', { joint_share: null }]] });
    expect(sharedChanges([shared], { fam: { on: true, names: 'Anastasia' } })).toEqual({ changes: [] });
    expect(sharedChanges([cash], { cash: { on: true, names: ' ' } }).error).toBe('Say who you share Cash ••6922 with.');
  });
});
