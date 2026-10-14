import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ProfileHub, hubRows } from './ProfilePanel.jsx';
import {
  AccountDetail, AccountsList, AddByHand, RemoveDialog, ShareDialog, accountMeta, balanceWords,
  BankMark, bankInitials, countedToast, parseShare, pillFor, updatedWords,
} from './AccountsPanel.jsx';
import { RulePanel, RulesPage, ruleWords } from './RulesPanel.jsx';
import { ChangeEmail, SecurityPage } from './SecurityPanel.jsx';

const html = (el) => renderToStaticMarkup(el);
const text = (el) => html(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const calm = (s) => {
  expect(s).not.toMatch(/[−-]\s?\$/);
  expect(s).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(s).not.toMatch(/NaN|undefined|null|\[object/);
  expect(s).not.toMatch(/danger|warning|overdue|error/i);
};
const primaries = (el) => (html(el).match(/pk-btn primary/g) ?? []).length;

const NOW = Date.parse('2026-10-13T16:05:00Z');
const base = {
  id: 'x', name: 'TD Chequing', bank_name: 'TD Chequing', nickname: '', mask: '4417',
  institution: 'TD', kind: 'chequing', source: 'plaid', status: 'up_to_date', counted: true,
  syncs: true, joint: false, joint_share: null, anchor: false, can_anchor: false,
  balance: 2340.18, owing: false, updated_at: '2026-10-13T16:00:00+00:00',
  disconnected_on: null, history_from: '2026-03-02', transactions: 388, item_id: 'td',
};
const visa = { ...base, id: 'visa', name: 'TD Visa', bank_name: 'TD Visa', mask: '1203',
               kind: 'card', owing: true, balance: 412.55 };
const tang = { ...base, id: 'sav', name: 'Tangerine Savings', institution: 'Tangerine', mask: '0932',
               kind: 'savings', balance: 6100, anchor: true, can_anchor: true };
const simplii = { ...base, id: 'sim', name: 'Simplii Chequing', institution: 'Simplii', mask: '6612',
                  balance: 1880, joint: true, joint_share: 50, status: 'joint' };
const amex = { ...visa, id: 'amex', name: 'Amex Business', institution: 'American Express',
               mask: '3008', balance: 96.4, counted: false, status: 'not_counted' };
const eq = { ...base, id: 'eq', name: 'EQ Bank', institution: 'EQ Bank', mask: '5521', balance: 900,
             status: 'retrying', updated_at: '2026-10-13T10:05:00+00:00' };
const ws = { ...base, id: 'ws', name: 'Wealthsimple Cash', institution: 'Wealthsimple', mask: '7710',
             balance: 1240, status: 'disconnected', disconnected_on: '2026-10-01', transactions: 214,
             history_from: '2026-07-04' };
const signIn = { ...visa, status: 'sign_in', updated_at: '2026-10-06T15:00:00+00:00' };
const meridian = { ...base, id: 'hand:1', name: 'Meridian Savings', bank_name: 'Meridian Savings',
                   mask: '', institution: '', kind: 'savings', source: 'hand', status: 'manual',
                   balance: 3000, updated_at: '2026-10-01', can_anchor: true, anchor: true,
                   history_from: null, transactions: 0, item_id: '' };

describe('S-01 the Profile hub', () => {
  const summary = { accounts: 6, needs_you: 1, rules: 4 };
  const user = { first_name: 'Alex', email: 'alex@example.com', passkeys: 1 };

  it('groups Money, You, Privacy and Help, with counts', () => {
    const groups = hubRows(summary, user);
    expect(groups.map((g) => g.title)).toEqual(['Money', 'You', 'Privacy', 'Help']);
    const [money, you] = groups;
    expect(money.rows[0]).toMatchObject({ name: 'Accounts', sub: '6 accounts', needs: 1 });
    expect(money.rows[1]).toMatchObject({ name: 'Categories and rules', sub: '4 saved rules' });
    expect(you.rows[0].sub).toBe('alex@example.com · 1 passkey');
  });

  it('every row opens something now: a page, or for Help the drafts as a sheet', () => {
    const t = text(<ProfileHub summary={summary} user={user} />);
    expect(t).toContain('Alex · alex@example.com');
    expect(t).toContain('1 needs you');
    expect(t).not.toContain('Coming soon');
    const rows = hubRows(summary, user).flatMap((g) => g.rows);
    expect(rows.filter((r) => r.soon)).toEqual([]);
    expect(rows.find((r) => r.key === 'help')).toMatchObject({ doc: 'help' });
    expect(rows.find((r) => r.key === 'legal')).toMatchObject({ doc: 'legal' });
    for (const key of ['notifications', 'consent', 'data', 'protect']) {
      expect(rows.find((r) => r.key === key).doc).toBeUndefined();
    }
    calm(t);
    expect(primaries(<ProfileHub summary={summary} user={user} />)).toBe(0);
  });

  it('an investing account she told Pearl about can be undone here (GR-37)', () => {
    const rows = hubRows({ ...summary, investing: { type: 'tfsa', label: 'TFSA' } }, user)[0].rows;
    expect(rows.at(-1)).toMatchObject({ key: 'investing', undo: true,
                                       sub: 'You told Pearl you opened one: TFSA' });
    const t = text(<ProfileHub summary={{ ...summary, investing: { type: 'tfsa', label: 'TFSA' } }} user={user} />);
    expect(t).toContain('Investing account');
    expect(t).toContain('Undo');
    expect(hubRows(summary, user)[0].rows.some((r) => r.key === 'investing')).toBe(false);
  });

  it('says nothing needs her when nothing does, and reads well before it loads', () => {
    const t = text(<ProfileHub summary={null} user={null} />);
    expect(t).not.toContain('needs you');
    expect(t).toContain('Link a bank or add a balance');
    calm(t);
  });
});

describe('AM-01 / C-01 the accounts', () => {
  it('says each account’s state the way the handoff does', () => {
    expect(accountMeta(base, NOW)).toBe('$2,340.18 · updated 5 minutes ago');
    expect(accountMeta(visa, NOW)).toBe('$412.55 owing · updated 5 minutes ago');
    expect(accountMeta(tang, NOW)).toBe('$6,100.00 · counts toward your Anchor');
    expect(accountMeta(simplii, NOW)).toBe('$1,880.00 · joint, your share is 50%');
    expect(accountMeta(amex, NOW)).toBe('$96.40 owing · not in your budget');
    expect(accountMeta(eq, NOW)).toBe('$900.00 · last updated 6 hours ago');
    expect(accountMeta(ws, NOW)).toBe('$1,240.00 · disconnected on October 1');
    expect(accountMeta(meridian, NOW)).toBe('$3,000.00 · you updated it October 1');
    expect(accountMeta(signIn, NOW)).toMatch(/^\$412\.55 owing · last updated \w+day, October 6$/);
  });

  it('never shows $0, a sign or a missing figure', () => {
    expect(balanceWords({ ...visa, balance: 0 })).toBe('Nothing owing');
    expect(balanceWords({ ...base, balance: -12.5 })).toBe('$12.50');
    expect(accountMeta({ ...base, balance: null, updated_at: null }, NOW))
      .toBe('Waiting for its first update');
    expect(updatedWords('nonsense', NOW)).toBeNull();
  });

  it('a pill for every state, in words', () => {
    expect([base, simplii, amex, meridian, signIn, eq, ws].map((a) => pillFor(a).label)).toEqual(
      ['Up to date', 'Joint', 'Not counted', 'Manual', 'Sign in again', 'We’re retrying', 'Disconnected']);
    expect(pillFor(signIn).tone).toBe('caution');
  });

  it('avatars from the bank', () => {
    expect(bankInitials(base)).toBe('TD');
    expect(bankInitials(tang)).toBe('T');
    expect(bankInitials(eq)).toBe('EQ');
  });

  const data = { linked: [base, visa, tang, simplii, amex, signIn, ws], added: [meridian],
                 plaid: { configured: true, encryption_ready: true }, currency_mix: [] };

  it('lists Linked and Added by you, with one primary action', () => {
    const el = <AccountsList data={data} now={NOW} />;
    const t = text(el);
    expect(t).toContain('Profile › Accounts'.replace(' › ', ' ')); // breadcrumb items
    expect(t).toContain('Linked');
    expect(t).toContain('Added by you');
    expect(t).toContain('TD Visa ••1203');
    expect(t.match(/Reconnect/g)).toHaveLength(2);
    expect(t).toContain('Link another bank');
    expect(t).toContain('Add a balance by hand');
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('an empty page offers to link', () => {
    const t = text(<AccountsList data={{ linked: [], added: [], plaid: {} }} now={NOW} />);
    expect(t).toContain('Link your bank');
    expect(t).toContain('isn’t set up');
    calm(t);
  });
});

describe('AM-02 to AM-07, C-06 one account', () => {
  it('AM-02: tiles and how it counts', () => {
    const el = <AccountDetail a={visa} now={NOW} />;
    const t = text(el);
    for (const s of ['TD Visa ••1203', 'Balance owing', '$412.55', 'Updated', '5 min ago',
      'History from', 'March 2026', 'How it counts', 'Count in my budget',
      'This is a joint account', 'Only your share counts. You choose the share.', 'Nickname',
      'Remove this account']) expect(t).toContain(s);
    expect(t).not.toContain('owing owing');
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('AM-03: not in the budget says what that means', () => {
    const t = text(<AccountDetail a={amex} now={NOW} />);
    expect(t).toContain('This account isn’t in your budget. Its transactions stay here, but they don’t count toward safe to spend, spending or your snapshot.');
    calm(t);
  });

  it('AM-03: the toast says what safe to spend is now', () => {
    expect(countedToast(amex, false, 738.58))
      .toBe('Amex Business no longer counts. Safe to spend is now $738.58.');
    expect(countedToast(amex, true, null)).toBe('Amex Business counts again.');
    expect(countedToast(amex, false, 0)).toBe('Amex Business no longer counts.');
  });

  it('AM-04: her share, between 1% and 99%', () => {
    const el = <ShareDialog a={simplii} />;
    const t = text(el);
    expect(t).toContain('Your share of Simplii Chequing');
    expect(t).toContain('Half (50%)');
    expect(t).toContain('A different share');
    expect(t).toContain('Between 1% and 99%');
    expect(primaries(el)).toBe(1);
    expect(parseShare(' 33.5 % ')).toBe(33.5);
    expect(Number.isNaN(parseShare('half'))).toBe(true);
    calm(t);
  });

  it('AM-05: add a balance by hand', () => {
    const el = <AddByHand />;
    const t = text(el);
    for (const s of ['Add a balance by hand', 'For a bank Pearl can’t link yet.', 'Chequing', 'Savings',
      'Credit card', 'Counts as money you owe', 'Balance today', 'Add account', 'Cancel']) {
      expect(t).toContain(s);
    }
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('AM-06: a balance added by hand', () => {
    const el = <AccountDetail a={meridian} now={NOW} />;
    const t = text(el);
    for (const s of ['Meridian Savings', 'Balance', '$3,000.00', 'You updated it', 'October 1',
      'Added by you. Pearl can’t see its transactions, so it only counts in your snapshot.',
      'Update balance', 'Count in my snapshot', 'Counts toward my Anchor', 'Savings accounts only',
      'Remove this account']) expect(t).toContain(s);
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('AM-07: remove, keeping or deleting its transactions', () => {
    const el = <RemoveDialog a={visa} />;
    const t = text(el);
    for (const s of ['Remove TD Visa?', 'Pearl stops syncing it and disconnects it from your bank straight away.',
      'Its 388 transactions', 'Keep them', 'Past months stay accurate. Nothing new comes in.',
      'Delete them too', 'Your averages will change. This can’t be undone.', 'Remove account',
      'Keep it']) expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);
    expect(text(<RemoveDialog a={meridian} />)).not.toContain('transactions');
  });

  it('C-06: a disconnected account', () => {
    const el = <AccountDetail a={ws} now={NOW} />;
    const t = text(el);
    for (const s of ['Disconnected on October 1. Your past transactions stay in Pearl, but new ones won’t come in.',
      'Balance on October 1', '$1,240.00', 'Transactions in Pearl', '214', 'History from', 'July 2026',
      'Reconnect', 'Keep it as a manual account',
      'Or remove this account and its history from Pearl.']) expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('a bank that wants a sign-in says so calmly', () => {
    const t = text(<AccountDetail a={signIn} now={NOW} />);
    expect(t).toContain('TD needs you to sign in again.');
    calm(t);
  });
});

describe('S-03 Categories and rules', () => {
  const rules = [
    { id: 'merchant:loblaws', kind: 'merchant', name: 'Loblaws', category: 'Groceries' },
    { id: 'destination:to:m', kind: 'destination', name: 'Transfers to M. Papas', category: 'Saved' },
    { id: 'merchant:x', kind: 'merchant', name: 'Bank fee', category: 'Transfers' },
    { id: 'exclusion:1', kind: 'exclusion', name: 'Staples', category: null, reason: 'Work', matched: 2 },
  ];

  it('lists each rule as "Always …", with the footnote', () => {
    expect(rules.map(ruleWords)).toEqual(['Always Groceries', 'Always Saved',
      'Always Between my accounts', 'Always left out']);
    const t = text(<RulesPage rules={rules} />);
    expect(t).toContain('When you sort something and tick “Remember”, Pearl sorts the next ones the same way. Your rules always win over ours.');
    expect(t).toContain('Deleting a rule doesn’t change transactions you’ve already sorted.');
    expect(t.match(/Edit/g)).toHaveLength(4);
    calm(t);
  });

  it('says so when there are none', () => {
    const t = text(<RulesPage rules={[]} />);
    expect(t).toContain('No saved rules yet');
    calm(t);
  });

  it('the edit panel: chips, Save, and delete', () => {
    const cats = [{ name: 'Groceries', group: 'essentials' }, { name: 'Dining', group: 'lifestyle' }];
    const el = <RulePanel rule={rules[0]} categories={cats} />;
    const t = text(el);
    expect(t).toContain('Pearl files every transaction from Loblaws as Groceries.');
    expect(t).toContain('Delete this rule');
    expect(primaries(el)).toBe(1);
    const out = text(<RulePanel rule={rules[3]} categories={cats} />);
    expect(out).toContain('It leaves out 2 transactions now.');
    expect(out).toContain('Removing it puts what it left out back into your spending.');
    calm(out);
  });
});

describe('Sign-in and security, and S-02', () => {
  const user = { email: 'alex@example.com', passkeys: 0, has_password: false,
                 onboarding: { consents: { terms: { value: true } } } };

  it('shows the email with Change, passkeys and sign out', () => {
    const t = text(<SecurityPage user={user} />);
    for (const s of ['Sign-in and security', 'alex@example.com', 'Change', 'Passkeys',
      'None yet. You sign in with a code sent to your email.', 'Sign out']) {
      expect(t).toContain(s);
    }
    // The choices from setup live on Privacy and consent now (THL-117 CN-04).
    expect(t).not.toContain('Your choices');
    expect(t).not.toContain('improve suggestions');
    calm(t);
  });

  it('S-02: current and new email, the hint, Send code', () => {
    const el = <ChangeEmail user={user} />;
    const t = text(el);
    for (const s of ['Profile', 'Sign-in and security', 'Email', 'Change your sign-in email',
      'Current email', 'New email',
      'We’ll send a 6-digit code to check it’s yours, and let your old email know.',
      'Send code', 'Cancel']) expect(t).toContain(s);
    expect(html(el)).toContain('value="alex@example.com"');
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('S-02: the code step', () => {
    const el = <ChangeEmail user={user} startAt="code" sentTo="alex.papas@example.com" />;
    const t = text(el);
    expect(t).toContain('We sent a 6-digit code to alex.papas@example.com. It works for 10 minutes.');
    expect(t).toContain('Use a different email');
    expect(primaries(el)).toBe(1);
    calm(t);
  });
});

describe('Accounts: logos and investment accounts', () => {
  const tfsa = { ...base, id: 'tfsa', name: 'Wealthsimple TFSA', institution: 'Wealthsimple',
                 mask: '3333', kind: 'investment', status: 'investment', counted: false,
                 syncs: false, balance: 18250, transactions: 0, history_from: null };

  it('shows the bank logo where Plaid has one, initials otherwise', () => {
    expect(html(<BankMark a={{ ...base, logo: 'data:image/png;base64,QUJD' }} />))
      .toContain('<img src="data:image/png;base64,QUJD"');
    expect(html(<BankMark a={base} />)).toContain('>TD<');
    expect(html(<AccountsList data={{ linked: [{ ...base, logo: 'data:image/png;base64,QUJD' }],
                                      added: [], plaid: {} }} now={NOW} />)).toContain('pf-logo');
  });

  it('an investment account is balance only, with no way to count it as spending', () => {
    expect(pillFor(tfsa)).toEqual({ label: 'Investments', tone: 'neutral', icon: null });
    expect(accountMeta(tfsa, NOW)).toBe('$18,250.00 · balance only');
    const t = text(<AccountDetail a={tfsa} now={NOW} />);
    expect(t).toContain('Money you move into it counts as saved, never as spending.');
    expect(t).not.toContain('Count in my budget');
    expect(t).not.toContain('isn’t in your budget');
    calm(t);
  });
});

describe('nicknames name the account everywhere', () => {
  it('accountTitle prefers her nickname', async () => {
    const { accountTitle } = await import('../api.js');
    const a = { account_id: 'chq', institution: 'TD', kind_label: 'Chequing', mask: '1111' };
    expect(accountTitle(a)).toBe('TD · Chequing ••1111');
    expect(accountTitle({ ...a, nickname: 'Bills account' })).toBe('Bills account');
    expect(accountTitle({ ...a, nickname: 'Bills account', joint: 'Sam' }))
      .toBe('Bills account · Joint with Sam');
  });
});
