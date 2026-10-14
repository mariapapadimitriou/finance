import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DOCS } from '../pearl/docs.jsx';
import Onboarding from '../pearl/Onboarding.jsx';
import {
  BEFORE_YOU_GO, agreedWords, consentDate, milestoneKey, shouldPrime,
} from '../pearl/privacy.jsx';
import { AiOffDialog, ConsentPage } from './ConsentPanel.jsx';
import {
  AccountDeleted, BeforeYouGo, ConfirmDelete, DataPage, firstMethod, readyWords, sizeWords,
} from './DataPanel.jsx';
import { NotificationsPage, TIMES, applyChange } from './NotificationsPanel.jsx';
import { PrimeSheet } from './NotifyPrime.jsx';
import { ProtectPage, connectionWords } from './ProtectPanel.jsx';

const html = (el) => renderToStaticMarkup(el);
const text = (el) => html(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const calm = (s) => {
  expect(s).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(s).not.toMatch(/NaN|undefined|null|\[object/);
  expect(s).not.toMatch(/danger|warning|overdue|error/i);
  expect(s).not.toMatch(/'/);              // curly apostrophes only
};
const primaries = (el) => (html(el).match(/(pk|p)-btn primary/g) ?? []).length;

const NOW = Date.parse('2026-10-13T16:05:00Z');
// Noon UTC on October 2, 2026, so the date reads the same in any time zone a
// test runs in.
const OCT2 = Date.parse('2026-10-02T12:00:00Z') / 1000;

const privacy = {
  consents: {
    terms: { value: true, at: OCT2 }, read_data: { value: true, at: OCT2 },
    insights: { value: true, at: OCT2 }, ai_sort: { value: true, at: OCT2 },
    tips: { value: false, at: OCT2 }, analytics: { value: true, at: null },
  },
  log: [],
  contact: 'privacy@pearl.example',
  email: 'alex@example.com',
  connections: [
    { item_id: 'td', institution: 'TD', accounts: 3, last_synced: '2026-10-13T16:00:00+00:00',
      state: 'healthy' },
    { item_id: 'eq', institution: 'EQ Bank', accounts: 1, last_synced: null,
      state: 'needs_sign_in' },
  ],
};

describe('THL-115 T-01 to T-04 How we protect you', () => {
  it('T-04: the trust points, her connections and a person to write to', () => {
    const el = <ProtectPage privacy={privacy} now={NOW} />;
    const t = text(el);
    for (const s of ['Profile', 'How we protect you',
      'What Pearl can and can’t do with your bank, and what happens to your data.',
      'Read-only access', 'Pearl can see your balances and transactions. That’s all.',
      'Pearl can’t move money', 'No payments, transfers or withdrawals, ever.',
      'We never see your bank password',
      'You sign in to your bank through Plaid, our connection partner.',
      'How signing in through Plaid works', 'What we store', 'See everything we store',
      'Who we share with', 'We don’t sell your data. We share only what’s needed to run Pearl.',
      'See who we share with', 'Your connections', 'TD · 3 accounts',
      'Read-only through Plaid · synced 5 minutes ago', 'Healthy', 'EQ Bank · 1 account',
      'Sign in again', 'Contact a person']) expect(t).toContain(s);
    expect(html(el)).toContain('href="mailto:privacy@pearl.example"');
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('T-04 with no banks and nobody to write to', () => {
    const t = text(<ProtectPage privacy={{ ...privacy, connections: [], contact: null }} />);
    expect(t).toContain('No banks are linked, so Pearl can’t see any.');
    expect(t).not.toContain('Contact a person');
    calm(t);
  });

  it('a connection never synced says only how it connects', () => {
    expect(connectionWords({ institution: 'EQ Bank', accounts: 0, last_synced: null }, NOW))
      .toEqual({ name: 'EQ Bank', sub: 'Read-only through Plaid' });
  });

  it('T-02 and T-03 say what is true, and point at Your data', () => {
    const store = text(DOCS.store.render());
    for (const s of ['What we store', 'Your data, plainly', 'We keep', 'We never keep', 'Where',
      'For how long', 'When you delete your account, we delete your data straight away',
      'You can download or delete your data any time in Profile › Your data.'])
      expect(store).toContain(s);
    expect(store).not.toContain('Start fresh');
    const share = text(DOCS.share.render());
    for (const s of ['Who sees your data', 'Plaid', 'Needed', 'Your choice', 'Unveil phase',
      'We don’t sell your data, and we don’t show you ads.']) expect(share).toContain(s);
    const legal = text(DOCS.legal.render());
    expect(legal).toContain('Privacy');
    expect(legal).toContain('Terms');
  });
});

describe('THL-117 consent moments in onboarding (CN-01 to CN-03)', () => {
  const at = (step, consents = {}) => (
    <Onboarding user={{ email: 'alex@example.com', passkeys: 1,
                        onboarding: { step, province: 'ON', consents } }} />
  );

  it('T-01: How we protect you, before linking', () => {
    const el = at('protect');
    const t = text(el);
    for (const s of ['Before you link', 'How we protect you', 'Step 4 of 6',
      'Your money stays yours.', 'You sign in to your bank through Plaid, our connection partner.',
      'Continue']) expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('CN-01 replaces the checkboxes with one agreement', () => {
    const el = at('consents');
    const t = text(el);
    for (const s of ['Before you link', 'Linking your bank', 'Step 5 of 6',
      'To work out what’s safe to spend, Pearl needs to read your balances and transactions.',
      'Pearl can', 'See your balances and transactions. Read-only.', 'Pearl can’t',
      'Move money, make payments or see your bank password.', 'Plaid connects us',
      'By continuing, you agree to the Terms and Privacy policy , and that Pearl can read the accounts you link.',
      'You’re in control.', 'Change your mind any time in Profile › Privacy and consent.',
      'Agree and continue']) expect(t).toContain(s);
    expect(html(el)).not.toContain('type="checkbox"');
    expect(t).not.toContain('improve suggestions');
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('CN-02: working out her numbers is needed; AI is hers to choose, nothing chosen', () => {
    const el = at('uses');
    const t = text(el);
    for (const s of ['Your accounts are linked', 'How Pearl uses your transactions',
      'To work out your numbers', 'so it’s needed to continue',
      'To sort them with AI (your choice)',
      'we send only the merchant, amount and date to our AI provider',
      'Yes, sort them with AI', 'Fewer things for you to check', 'No thanks',
      'We’ll use your bank’s categories and your rules', 'Your numbers, your call.',
      'Pearl only uses your transactions for you.', 'Continue']) expect(t).toContain(s);
    expect(html(el)).not.toMatch(/type="radio"[^>]*checked/);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('CN-03: tips by email, unticked', () => {
    const el = at('email');
    const t = text(el);
    for (const s of ['Almost done', 'One last thing', 'Send me tips and news from Pearl',
      'About once a month. Unsubscribe any time.',
      'We’ll always email you about your account, like sign-in codes and security alerts, whether or not you tick this.',
      'Change this any time in Profile › Privacy and consent.', 'Finish']) expect(t).toContain(s);
    expect(html(el)).not.toMatch(/type="checkbox"[^>]*checked/);
    expect(primaries(el)).toBe(1);
    calm(t);
  });
});

describe('THL-117 CN-04 / CN-05 Privacy and consent', () => {
  it('CN-04: each consent with its date, and her rights', () => {
    const el = <ConsentPage privacy={privacy} />;
    const t = text(el);
    for (const s of ['Profile', 'Privacy and consent', 'What you’ve agreed to. Change your mind any time.',
      'Needed for Pearl to work', 'Reading your linked accounts', 'Agreed October 2, 2026',
      'Manage accounts', 'Working out your numbers', 'Withdraw', 'Your choice',
      'Sorting transactions with AI', 'Agreed October 2, 2026 · merchant, amount and date only',
      'Tips and news by email', 'Not agreed', 'Help improve Pearl',
      'Anonymous usage data. Never amounts, merchants or account details.', 'Your rights',
      'See or correct what we hold', 'Our privacy officer replies within 30 days', 'Ask',
      'Privacy policy', 'Plain-language draft · October 2026', 'Read']) expect(t).toContain(s);
    // AI on, tips off, usage data on.
    expect((html(el).match(/type="checkbox" checked=""/g) ?? []).length).toBe(2);
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('CN-04 without a contact leaves out Ask', () => {
    expect(text(<ConsentPage privacy={{ ...privacy, contact: null }} />)).not.toContain('See or correct');
  });

  it('CN-05: turning AI sorting off asks first', () => {
    const el = <AiOffDialog onClose={() => {}} onConfirm={() => {}} />;
    const t = text(el);
    for (const s of ['Turn off AI sorting?',
      'From now on, Pearl uses your bank’s categories and your rules. Nothing new is sent to our AI provider.',
      'What changes', 'More transactions may land in “needs a look”.', 'What stays',
      'Everything already sorted keeps its category.', 'Turn it off', 'Keep it on'])
      expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('dates and words', () => {
    expect(consentDate(OCT2)).toBe('October 2, 2026');
    expect(consentDate(null)).toBe('');
    expect(agreedWords({ value: true, at: null })).toBe('Agreed');
    expect(agreedWords({ value: false, at: OCT2 })).toBe('Not agreed');
    expect(agreedWords(undefined)).toBe('Not agreed');
  });
});

describe('THL-116 D-01 to D-05 Your data', () => {
  it('D-01: a copy, or close the account', () => {
    const el = <DataPage />;
    const t = text(el);
    for (const s of ['Profile', 'Your data', 'It’s yours. Take a copy any time, or close your account.',
      'Download a copy',
      'A spreadsheet of your accounts and every transaction in Pearl, with the categories you chose.',
      'Download my data', 'Delete your account',
      'Disconnects your banks and deletes your data straight away.', 'Delete my account'])
      expect(t).toContain(s);
    expect(t).not.toContain('within 30 days');
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('D-02: the download is ready', () => {
    const el = <DataPage summary={{ accounts: 6, transactions: 1306, bytes: 86016 }} />;
    const t = text(el);
    expect(t).toContain('Your download is ready: 6 accounts and 1,306 transactions.');
    expect(t).toContain('Download .zip (84 KB)');
    expect(html(el)).toContain('/api/data/export.zip');
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('D-02 never says nothing or NaN', () => {
    expect(readyWords({ accounts: 1, transactions: 0 }))
      .toBe('Your download is ready: 1 account and 0 transactions.');
    expect(sizeWords(0)).toBeNull();
    expect(sizeWords(undefined)).toBeNull();
    expect(sizeWords(200)).toBe('1 KB');
    expect(sizeWords(3 * 1024 * 1024)).toBe('3.0 MB');
    const t = text(<DataPage summary={{ accounts: 0, transactions: 0, bytes: 0 }} />);
    expect(t).toContain('Download .zip');
    calm(t);
  });

  it('D-03: exactly what happens, and when', () => {
    const el = <BeforeYouGo />;
    const t = text(el);
    for (const s of ['Profile', 'Your data', 'Delete account', 'Before you go',
      'Here’s exactly what happens if you delete your account.', 'Right away',
      'We disconnect all your banks. Pearl can’t see them any more.',
      'You’re signed out on every device.',
      'We delete your accounts, transactions, goals and settings.', 'Within 30 days',
      'What we keep',
      'A record that your account existed and when it was deleted, because the law asks us to.',
      'Want a copy first? Download your data before you go.', 'Download', 'Continue',
      'Keep my account']) expect(t).toContain(s);
    expect(BEFORE_YOU_GO).toHaveLength(5);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('D-04: a passkey first, an email code instead', () => {
    const options = { methods: ['passkey', 'code'], passkeys: 1, email: 'alex@example.com' };
    const el = <ConfirmDelete options={options} method="passkey" />;
    const t = text(el);
    for (const s of ['Confirm it’s you',
      'Use your passkey to delete your account. This can’t be undone.', 'Delete my account',
      'Use an email code instead', 'Cancel']) expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);

    const code = <ConfirmDelete options={options} method="code" sentTo="alex@example.com" code="12" />;
    const ct = text(code);
    expect(ct).toContain('We sent a 6-digit code to alex@example.com. Enter it to delete your account. This can’t be undone.');
    expect(ct).toContain('Send a new code');
    expect(ct).toContain('Use your passkey instead');
    expect(primaries(code)).toBe(1);
    calm(ct);
  });

  it('D-04: which way first', () => {
    expect(firstMethod({ methods: ['passkey', 'code'] }, true)).toBe('passkey');
    expect(firstMethod({ methods: ['passkey', 'code'] }, false)).toBe('code');
    expect(firstMethod({ methods: ['password'] }, true)).toBe('password');
    expect(firstMethod({ methods: [] }, true)).toBeNull();
  });

  it('D-05: deleted, and where the confirmation went', () => {
    const el = <AccountDeleted sentTo="alex@example.com" />;
    const t = text(el);
    for (const s of ['Your account is deleted',
      'We’ve disconnected your banks, signed you out and deleted your data.',
      'We’ve sent a confirmation to alex@example.com.', 'Close']) expect(t).toContain(s);
    expect(primaries(el)).toBe(0);
    calm(t);
    expect(text(<AccountDeleted sentTo={null} />)).not.toContain('sent a confirmation');
  });
});

describe('THL-139 N-01 / N-02 Notifications', () => {
  const prefs = {
    types: { payday: { phone: true, email: true }, weekly: { phone: true, email: false },
             progress: { phone: true, email: false }, milestones: { phone: true, email: true },
             bank: { phone: true, email: true } },
    quiet: { from: '21:00', to: '08:00' }, lock_amounts: false,
    prompt: { answer: null, asked: 0, milestone: null },
  };

  it('N-02: each kind by phone and email, quiet hours, lock screen', () => {
    const el = <NotificationsPage data={{ prefs, email_ok: true }} />;
    const t = text(el);
    for (const s of ['Profile', 'Notifications',
      'We only nudge you at useful moments: at most 3 a week, never about overspending.',
      'What you get', 'Payday', 'A nudge to set something aside when your pay lands',
      'Weekly check-in', 'Sundays at 10 am', 'Progress',
      'Your Anchor or a treasure chest at 25, 50 and 75%', 'Milestones',
      'When something new opens on your path', 'Bank needs you',
      'When a bank needs you to sign in again', 'Phone', 'Email', 'Quiet hours', 'From', 'To',
      'Lock screen', 'Show amounts on my lock screen',
      'Off: “Your pay arrived.” On: “Your pay of $2,140 arrived.”',
      'Phone notifications come from Pearl’s iPhone app, which isn’t out yet.'])
      expect(t).toContain(s);
    // 5 phone + 3 email ticked, as drawn.
    expect((html(el).match(/type="checkbox" checked=""/g) ?? []).length).toBe(8);
    expect(html(el)).toMatch(/<option value="21:00" selected="">9:00 pm<\/option>/);
    expect(html(el)).toMatch(/<option value="08:00" selected="">8:00 am<\/option>/);
    expect(t).not.toContain('Turn it on in Privacy and consent');
    expect(primaries(el)).toBe(0);
    calm(t);
  });

  it('N-02: email waits for a yes to email from Pearl', () => {
    const el = <NotificationsPage data={{ prefs, email_ok: false }} />;
    expect(text(el)).toContain('Turn it on in Privacy and consent');
    expect((html(el).match(/type="checkbox" checked=""/g) ?? []).length).toBe(5);
    expect((html(el).match(/type="checkbox" disabled=""/g) ?? []).length).toBe(5);
  });

  it('times and changes', () => {
    expect(TIMES[0]).toEqual({ value: '00:00', label: '12:00 am' });
    expect(TIMES[25]).toEqual({ value: '12:30', label: '12:30 pm' });
    const next = applyChange(prefs, { types: { weekly: { email: true } }, quiet: { to: '07:30' } });
    expect(next.types.weekly).toEqual({ phone: true, email: true });
    expect(next.quiet).toEqual({ from: '21:00', to: '07:30' });
    expect(prefs.types.weekly.email).toBe(false);
  });

  it('N-01: the priming sheet', () => {
    const el = <PrimeSheet onOn={() => {}} onNotNow={() => {}} />;
    const t = text(el);
    for (const s of ['Want a heads-up at the right moments?', 'Payday',
      'A nudge to set something aside', 'Weekly check-in', 'Your week in one minute, on Sundays',
      'Progress and milestones', 'When your Anchor grows or a step opens', 'Bank needs you',
      'When a bank asks you to sign in again',
      'Never about overspending. No amounts on your lock screen. Quiet from 9 pm to 8 am.',
      'Turn on notifications', 'Not now']) expect(t).toContain(s);
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('N-01: after the first safe to spend, and once more after a milestone', () => {
    const ok = { state: 'ok' };
    const path = { phase: 'protect', steps: [{ done: true }, { done: false }] };
    expect(milestoneKey(path)).toBe('protect:1');
    expect(shouldPrime({ answer: null, asked: 0 }, ok, path)).toBe(true);
    expect(shouldPrime({ answer: null, asked: 0 }, { state: 'no_data' }, path)).toBe(false);
    expect(shouldPrime({ answer: 'on', asked: 1 }, ok, path)).toBe(false);
    const later = { answer: 'not_now', asked: 1, milestone: 'protect:1' };
    expect(shouldPrime(later, ok, path)).toBe(false);
    const moved = { phase: 'protect', steps: [{ done: true }, { done: true }] };
    expect(shouldPrime(later, ok, moved)).toBe(true);
    expect(shouldPrime({ ...later, asked: 2 }, ok, moved)).toBe(false);
  });
});

describe('Your data › Start over', () => {
  it('sits on Your data between the download and deleting the account', async () => {
    const { DataPage } = await import('./DataPanel.jsx');
    const t = text(<DataPage onStartOver={() => {}} onDelete={() => {}} />);
    expect(t).toContain('Start over');
    expect(t.indexOf('Download a copy')).toBeLessThan(t.indexOf('Start over'));
    expect(t.indexOf('Start over')).toBeLessThan(t.indexOf('Delete your account'));
    calm(t);
  });

  it('says what goes and what stays, and offers a copy first', async () => {
    const { BeforeYouStart } = await import('./DataPanel.jsx');
    const el = <BeforeYouStart onBack={() => {}} onContinue={() => {}} onDownload={() => {}} />;
    const t = text(el);
    for (const s of ['Every transaction, and everything you sorted', 'Your rules, your income and bills setup, and your budgets',
      'Your banks stay connected', 'Your goals and treasure chests', 'Download your data before you start over',
      'Continue', 'Keep everything']) {
      expect(t).toContain(s);
    }
    expect(primaries(el)).toBe(1);
    calm(t);
  });

  it('is confirmed only by typing “start over”', async () => {
    const { ConfirmStartOver, startOverReady } = await import('./DataPanel.jsx');
    expect(startOverReady('start over')).toBe(true);
    expect(startOverReady('  Start   Over ')).toBe(true);
    expect(startOverReady('start')).toBe(false);
    expect(startOverReady('')).toBe(false);
    const off = html(<ConfirmStartOver typed="" onTyped={() => {}} onConfirm={() => {}} onClose={() => {}} />);
    expect(off).toMatch(/disabled=""[^>]*>Start over</);
    const on = html(<ConfirmStartOver typed="start over" onTyped={() => {}} onConfirm={() => {}} onClose={() => {}} />);
    expect(on).not.toMatch(/disabled=""[^>]*>Start over</);
    expect(primaries(<ConfirmStartOver typed="start over" onTyped={() => {}} />)).toBe(1);
  });

  it('then says the history is downloading, and what came back', async () => {
    const { StartedOver } = await import('./DataPanel.jsx');
    expect(text(<StartedOver syncing />)).toContain('Downloading your history');
    expect(text(<StartedOver imported={1306} />)).toContain('1,306 transactions are back, ready to sort.');
    expect(text(<StartedOver imported={1} />)).toContain('1 transaction is back');
    const none = text(<StartedOver imported={0} />);
    expect(none).toContain('the next time it checks your banks');
    calm(none);
  });
});
