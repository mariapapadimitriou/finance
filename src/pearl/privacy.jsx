import { TrustPoint } from './ui.jsx';

/**
 * What onboarding and Profile › Privacy say alike, so the two never drift:
 *
 * - THL-115 T-01 (onboarding) and T-04 (Profile › How we protect you): the
 *   five trust points, with T-02 / T-03 behind two of them (docs.jsx).
 * - THL-117 CN-01 Linking your bank, CN-02 How Pearl uses your transactions,
 *   CN-03 One last thing; their answers show on CN-04 Privacy and consent.
 * - THL-139 N-01's four moments and N-02's five kinds of notification.
 * - THL-116 D-03 Before you go: what deleting the account does, and when.
 *
 * Where the design promises more than is true today ("kept in Canada", "deletes
 * your data within 30 days"), the words say what Pearl actually does.
 */

/** T-01 / T-04. `onDoc` opens 'plaid', 'store' or 'share' (docs.jsx). */
export function ProtectPoints({ onDoc }) {
  return (
    <div className="p-points">
      <TrustPoint icon="eye" title="Read-only access">
        Pearl can see your balances and transactions. That’s all.
      </TrustPoint>
      <TrustPoint icon="ban" title="Pearl can’t move money">
        No payments, transfers or withdrawals, ever.
      </TrustPoint>
      <TrustPoint icon="key" title="We never see your bank password"
                  link="How signing in through Plaid works" onLink={() => onDoc?.('plaid')}>
        You sign in to your bank through Plaid, our connection partner. Your login goes to
        your bank, not to us.
      </TrustPoint>
      <TrustPoint icon="database" title="What we store"
                  link="See everything we store" onLink={() => onDoc?.('store')}>
        Account names, balances and transactions. Encrypted when stored and when they move.
      </TrustPoint>
      <TrustPoint icon="users" title="Who we share with"
                  link="See who we share with" onLink={() => onDoc?.('share')}>
        We don’t sell your data. We share only what’s needed to run Pearl.
      </TrustPoint>
    </div>
  );
}

/** A card of rows, each a title and a line under it (CN-01, D-03, CN-05, N-01). */
export function Rows({ rows, label }) {
  return (
    <ul className="p-rows" aria-label={label}>
      {rows.map((r) => (
        <li key={`${r.title}-${r.sub}`}>
          <span className="p-rows-title">{r.title}</span>
          <span className="p-rows-sub">{r.sub}</span>
        </li>
      ))}
    </ul>
  );
}

// ── CN-01 Linking your bank (replaces O-07's checkboxes) ────────────────────
export const LINKING = {
  eyebrow: 'Before you link',
  title: 'Linking your bank',
  sub: 'To work out your Allowance, Pearl needs to read your balances and transactions.',
  rows: [
    { title: 'Pearl can', sub: 'See your balances and transactions. Read-only.' },
    { title: 'Pearl can’t', sub: 'Move money, make payments or see your bank password.' },
    { title: 'Plaid connects us',
      sub: 'A service banks and apps use to share data safely. Its privacy policy applies too.' },
  ],
  agree: 'Agree and continue',
};

// ── CN-02 How Pearl uses your transactions (after linking) ──────────────────
export const USES = {
  eyebrow: 'Your accounts are linked',
  title: 'How Pearl uses your transactions',
  needTitle: 'To work out your numbers',
  need: 'Pearl looks at your income, bills and spending to find your Allowance and '
    + 'your next step. This is what Pearl does, so it’s needed to continue.',
  aiTitle: 'To sort them with AI (your choice)',
  ai: 'For transactions Pearl isn’t sure about, we send only the merchant, amount and date '
    + 'to our AI provider. Never your name, account numbers or balances. It may be processed '
    + 'outside Canada, and the provider can’t keep it or train on it.',
  yes: { label: 'Yes, sort them with AI', description: 'Fewer things for you to check' },
  no: { label: 'No thanks', description: 'We’ll use your bank’s categories and your rules' },
};

// ── CN-03 One last thing (marketing email, unticked) ────────────────────────
export const TIPS = {
  eyebrow: 'Almost done',
  title: 'One last thing',
  label: 'Send me tips and news from Pearl',
  description: 'About once a month. Unsubscribe any time.',
  foot: 'We’ll always email you about your account, like sign-in codes and security alerts, '
    + 'whether or not you tick this.',
};

// ── CN-05 Turn off AI sorting? ─────────────────────────────────────────────
export const AI_OFF = {
  title: 'Turn off AI sorting?',
  body: 'From now on, Pearl uses your bank’s categories and your rules. Nothing new is sent '
    + 'to our AI provider.',
  rows: [
    { title: 'What changes', sub: 'More transactions may land in “needs a look”.' },
    { title: 'What stays', sub: 'Everything already sorted keeps its category.' },
  ],
};

// ── D-03 Before you go ──────────────────────────────────────────────────────
// Deleting is immediate here, so only the host's backups take up to 30 days.
export const BEFORE_YOU_GO = [
  { title: 'Right away', sub: 'We disconnect all your banks. Pearl can’t see them any more.' },
  { title: 'Right away', sub: 'You’re signed out on every device.' },
  { title: 'Right away', sub: 'We delete your accounts, transactions, goals and settings.' },
  { title: 'Within 30 days', sub: 'The last copies in our host’s backups are gone too.' },
  { title: 'What we keep',
    sub: 'A record that your account existed and when it was deleted, because the law asks us to.' },
];

// ── N-01 / N-02 ─────────────────────────────────────────────────────────────
export const PRIME_ROWS = [
  { title: 'Payday', sub: 'A nudge to set something aside' },
  { title: 'Weekly check-in', sub: 'Your week in one minute, on Sundays' },
  { title: 'Progress and milestones', sub: 'When your Anchor grows or a step opens' },
  { title: 'Bank needs you', sub: 'When a bank asks you to sign in again' },
];
export const PRIME_FOOT = 'Never about overspending. No amounts on your lock screen. '
  + 'Quiet from 9 pm to 8 am.';

export const NOTIFY_TYPES = [
  { key: 'payday', title: 'Payday', sub: 'A nudge to set something aside when your pay lands' },
  { key: 'weekly', title: 'Weekly check-in', sub: 'Sundays at 10 am' },
  { key: 'progress', title: 'Progress', sub: 'Your Anchor or a treasure chest at 25, 50 and 75%' },
  { key: 'milestones', title: 'Milestones', sub: 'When something new opens on your path' },
  { key: 'bank', title: 'Bank needs you', sub: 'When a bank needs you to sign in again' },
];

/** Where she is on her path, as a key that changes when a step is done. */
export function milestoneKey(path) {
  if (!path?.phase) return null;
  const done = (path.steps ?? []).filter((s) => s.done).length;
  return `${path.phase}:${done}`;
}

/**
 * N-01 shows once safe to spend has a number, and again only once after a
 * "Not now" — when she has reached a milestone since (THL-139). Never twice
 * after that; Settings is where it changes then.
 */
export function shouldPrime(prompt, sts, path) {
  if (sts?.state !== 'ok') return false;
  const p = prompt ?? {};
  if (!p.answer) return (p.asked ?? 0) === 0;
  if (p.answer !== 'not_now' || (p.asked ?? 0) >= 2) return false;
  const now = milestoneKey(path);
  return !!now && !!p.milestone && now !== p.milestone;
}

// ── Dates on CN-04 ──────────────────────────────────────────────────────────
const DATE = new Intl.DateTimeFormat('en-CA', { month: 'long', day: 'numeric', year: 'numeric' });

/** "October 2, 2026", from the seconds the server keeps; '' if none. */
export function consentDate(at) {
  const n = Number(at);
  if (!at || !Number.isFinite(n)) return '';
  return DATE.format(new Date(n * 1000));
}

/** A row's "Agreed October 2, 2026" or "Not agreed". */
export function agreedWords(c) {
  if (!c?.value) return 'Not agreed';
  const on = consentDate(c.at);
  return on ? `Agreed ${on}` : 'Agreed';
}
