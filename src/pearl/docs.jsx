import { Banner, Heading, Sheet } from './ui.jsx';

/**
 * The detail sheets: what Pearl stores (T-02), who sees it (T-03), and the
 * footer's Privacy, Terms and Help.
 *
 * Written to describe what this app actually does. Where the design promises
 * more than is true today — data centres in Canada, a download of your data —
 * the copy says what is true instead.
 */

function Facts({ rows }) {
  return (
    <div className="p-facts">
      {rows.map((r) => (
        <div className="p-fact" key={r.label}>
          <div className="grow">
            <p className="p-eyebrow">{r.label}</p>
            <span>{r.text}</span>
          </div>
          {r.tag && <span className={`tag${r.needed ? ' needed' : ''}`}>{r.tag}</span>}
        </div>
      ))}
    </div>
  );
}

const STORE_ROWS = [
  { label: 'We keep', text: 'Account names and types, balances, transactions, and the categories and goals you set' },
  { label: 'We never keep', text: 'Your bank username or password, or full card or account numbers' },
  { label: 'Where', text: 'Our cloud database, encrypted when stored and when it moves. Bank connections are encrypted again with a key only Pearl holds.' },
  { label: 'For how long', text: 'While you use Pearl. You can erase everything any time from Connections → Start fresh, which also disconnects your banks.' },
];

const SHARE_ROWS = [
  { label: 'Plaid', text: 'Connects to your bank, read-only', tag: 'Needed', needed: true },
  { label: 'Our cloud host', text: 'Runs Pearl and stores your data (Vercel and Neon)', tag: 'Needed', needed: true },
  { label: 'Our email service', text: 'Delivers your sign-in codes', tag: 'Needed', needed: true },
  { label: 'An investing partner', text: 'Only if you choose to go there in the Pearl phase. We always ask first.', tag: 'Your choice' },
];

export const DOCS = {
  store: {
    label: 'What we store',
    render: () => (
      <>
        <Heading level={2} eyebrow="What we store" title="Your data, plainly" />
        <Facts rows={STORE_ROWS} />
      </>
    ),
  },
  share: {
    label: 'Who we share with',
    render: () => (
      <>
        <Heading level={2} eyebrow="Who we share with" title="Who sees your data" />
        <Facts rows={SHARE_ROWS} />
        <Banner tone="positive">We never sell your data.</Banner>
      </>
    ),
  },
  plaid: {
    label: 'Signing in through Plaid',
    render: () => (
      <>
        <Heading level={2} eyebrow="Linking a bank" title="How signing in through Plaid works" />
        <div className="p-prose">
          <p>When you link a bank, Plaid opens in its own secure window. You sign in to
            your bank there, and your username and password go to your bank — Pearl never
            sees them.</p>
          <p>Your bank then lets Plaid share a read-only view: your accounts, their
            balances and your transactions. Pearl can&apos;t move money, make payments or
            change anything at your bank.</p>
          <p>You can disconnect a bank any time from Connections, and Pearl stops
            receiving anything from it.</p>
        </div>
      </>
    ),
  },
  privacy: {
    label: 'Privacy',
    render: () => (
      <>
        <Heading level={2} eyebrow="Draft" title="Privacy" />
        <div className="p-prose">
          <p>This is a plain-language draft, not yet a formal policy.</p>
        </div>
        <Facts rows={STORE_ROWS} />
        <Facts rows={SHARE_ROWS} />
      </>
    ),
  },
  terms: {
    label: 'Terms',
    render: () => (
      <>
        <Heading level={2} eyebrow="Draft" title="Terms" />
        <div className="p-prose">
          <p>This is a plain-language draft, not yet formal terms of service.</p>
          <h4>What Pearl is</h4>
          <p>Pearl helps you see what&apos;s safe to spend and plan what&apos;s next. It reads
            your accounts; it doesn&apos;t move money, and it isn&apos;t financial advice.</p>
          <h4>Your part</h4>
          <p>Keep your email and devices secure, since a code sent to your email or a
            passkey on your device is how you get in.</p>
          <h4>Ending</h4>
          <p>You can stop any time. Start fresh erases your data and disconnects your banks.</p>
        </div>
      </>
    ),
  },
  help: {
    label: 'Help',
    render: () => (
      <>
        <Heading level={2} eyebrow="Help" title="Getting in" />
        <div className="p-prose">
          <h4>Signing in</h4>
          <p>Use the passkey on this device, or ask for a 6-digit code by email. Codes work
            for 10 minutes; ask for a new one if yours has run out.</p>
          <h4>New phone or computer?</h4>
          <p>Sign in with an email code, then add a passkey on that device.</p>
          <h4>Too many tries?</h4>
          <p>Sign-in pauses for 15 minutes after too many attempts. Nothing about your
            money changes while it&apos;s paused.</p>
        </div>
      </>
    ),
  },
};

/** One open sheet, by name; `back` returns to the screen it was opened from. */
export function DocSheet({ name, onClose, backLabel }) {
  const doc = DOCS[name];
  if (!doc) return null;
  return (
    <Sheet label={doc.label} onClose={onClose} onBack={backLabel ? onClose : undefined}
           backLabel={backLabel}>
      {doc.render()}
      <button type="button" className="p-btn primary" onClick={onClose}>Got it</button>
    </Sheet>
  );
}
