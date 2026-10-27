import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  changePassword, getAuthStatus, getDevices, makeRecoveryCodes, passkeyRegister, passkeyRegisterOptions,
  removeDevice, startEmailChange, verifyEmailChange,
} from '../api.js';
import { usedWords } from '../pearl/SignedOut.jsx';
import { Alert, DetailPanel, PButton, Toast } from '../pearl/kit.jsx';
import { CodeInput } from '../pearl/ui.jsx';
import { createPasskey, passkeysSupported } from '../pearl/webauthn.js';
import { Field } from './GoalsParts.jsx';
import { ListRow, PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Sign-in and security (replaces the old Sign-in page), and S-02
 * Change your sign-in email.
 *
 * What she signs in with: her email (with Change, S-02), passkeys, a
 * password if her account has one, and signing out. The choices from setup
 * moved to Privacy and consent (THL-117 CN-04, ConsentPanel.jsx).
 *
 * Changing the email sends a 6-digit code to the new address — the same code
 * rules as signing in (ten minutes, five tries, a pause after too many) — and
 * lets the old address know once it's done.
 *
 * Recovery codes are for a sign-in on a new device when her other one isn't
 * to hand (A-07): ten, shown once, each working once.
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'Sign-in and security' }];

export function SecurityPage({ user, mail, onTab, onChangeEmail, onPasskey, passkeyBusy = false,
                               canPasskey = false, onRecovery, onSignOut, children = null }) {
  const n = user?.passkeys ?? 0;
  const codes = user?.recovery_codes ?? 0;
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={TRAIL} title="Sign-in and security" onTab={onTab} />
      <section className="pf-section" aria-labelledby="sc-signin">
        <h2 className="pk-h3" id="sc-signin">How you sign in</h2>
        <ul className="pf-list">
          <ListRow name="Email" sub={user?.email || 'None yet'} onOpen={onChangeEmail}
                   end={<span className="pf-end-link">Change</span>} />
          <ListRow name="Passkeys" chevron={false}
                   sub={n === 0 ? 'None yet. You sign in with a code sent to your email.'
                     : `${n} saved. Sign in with one tap on ${n === 1 ? 'that device' : 'those devices'}.`}
                   onOpen={canPasskey ? onPasskey : undefined}
                   end={canPasskey && (
                     <span className="pf-end-link">{passkeyBusy ? 'Waiting…' : 'Add one on this device'}</span>
                   )} />
          <ListRow name="Recovery codes" chevron={false} onOpen={onRecovery}
                   sub={codes === 0
                     ? 'None yet. For signing in on a new device when your other one isn’t to hand.'
                     : `${codes} of 10 left. Each works once.`}
                   end={<span className="pf-end-link">{codes === 0 ? 'Make codes' : 'Make new ones'}</span>} />
        </ul>
        {mail === false && (
          <p className="pf-foot">Email isn’t set up on this copy of Pearl yet, so codes print to the server’s log.</p>
        )}
      </section>
      {children}
      <div className="pf-stack">
        <PButton variant="secondary" onClick={onSignOut}>Sign out</PButton>
      </div>
    </div>
  );
}

/**
 * The devices signed in as her (2026-10-26): each one she confirmed, this one
 * first. Removing one signs it out, and it's never asked "Is this you signing
 * in?" again until she signs in on it and confirms it.
 */
export function DevicesSection({ devices = [], busy = false, onRemove }) {
  if (!devices.length) return null;
  return (
    <section className="pf-section" aria-labelledby="sc-devices">
      <h2 className="pk-h3" id="sc-devices">Your devices</h2>
      <p className="pk-muted">Signed in as you. These are asked to approve a sign-in somewhere new.
        Remove any that isn’t yours.</p>
      <ul className="pf-list">
        {devices.map((d) => (
          <ListRow key={d.id} name={d.label || 'A browser'} chevron={false}
                   sub={d.this ? 'This device' : usedWords(d.last_used_at).replace(/^used/, 'Used')}
                   onOpen={d.this || !onRemove || busy ? undefined : () => onRemove(d)}
                   end={!d.this && onRemove && <span className="pf-end-link">Remove</span>} />
        ))}
      </ul>
    </section>
  );
}

/** Accounts from before Pearl can still have a password. */
function PasswordForm({ onDone }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await changePassword(current, next);
      if (!r.ok) throw new Error(r.error || 'That didn’t work. Try again.');
      setCurrent('');
      setNext('');
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="pf-section" aria-labelledby="sc-pw">
      <h2 className="pk-h3" id="sc-pw">Password</h2>
      <form className="pf-form" onSubmit={save}>
        <Field label="Current password" id="sc-pw-current">
          <input id="sc-pw-current" type="password" autoComplete="current-password" required
                 value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password (at least 10 characters)" id="sc-pw-new" error={error}>
          <input id="sc-pw-new" type="password" autoComplete="new-password" minLength={10} required
                 value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <div className="pf-stack">
          <PButton variant="secondary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Change password'}
          </PButton>
        </div>
      </form>
    </section>
  );
}

/** Recovery codes: new ones replace the old, so that's asked first. */
export function RecoveryCodes({ had = 0, onClose, onMade }) {
  const [codes, setCodes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const make = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await makeRecoveryCodes();
      setCodes(r.codes);
      onMade?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <DetailPanel label="Recovery codes" overline="Sign-in and security" onClose={onClose}>
      {codes ? (
        <>
          <h1 className="pk-h2">Your recovery codes</h1>
          <p className="pk-muted">Keep them somewhere safe, like a password manager. Each works
            once, and you won’t see them again here.</p>
          <ul className="sc-codes" aria-label="Recovery codes">
            {codes.map((c) => <li key={c}>{c}</li>)}
          </ul>
          <div className="pf-stack">
            <PButton variant="secondary" onClick={() => {
              navigator.clipboard?.writeText(codes.join('\n')).then(() => setCopied(true))
                .catch(() => {});
            }}>{copied ? 'Copied' : 'Copy codes'}</PButton>
            <PButton onClick={onClose}>Done</PButton>
          </div>
        </>
      ) : (
        <>
          <h1 className="pk-h2">{had > 0 ? 'Make new recovery codes?' : 'Make recovery codes'}</h1>
          <p className="pk-muted">
            {had > 0
              ? 'The codes you have now stop working, so throw them away once you’ve saved the new ones.'
              : 'If you sign in on a new device and your other one isn’t to hand, one of these confirms it’s you. You get ten, and each works once.'}
          </p>
          {error && <Alert tone="caution">{error}</Alert>}
          <div className="pf-stack">
            <PButton disabled={busy} onClick={make}>
              {busy ? 'Making…' : had > 0 ? 'Make new codes' : 'Make codes'}
            </PButton>
            <PButton variant="text" onClick={onClose}>Cancel</PButton>
          </div>
        </>
      )}
    </DetailPanel>
  );
}

const pad = (s) => `0:${String(s).padStart(2, '0')}`;

/** S-02: the new address, then the code sent to it. */
export function ChangeEmail({ user, onTab, onBack, onDone, startAt = 'email', sentTo = '' }) {
  const [step, setStep] = useState(startAt);
  const [email, setEmail] = useState(sentTo);
  const [code, setCode] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [resendIn, setResendIn] = useState(0);
  useEffect(() => {
    if (resendIn <= 0) return undefined;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  async function send(e) {
    e?.preventDefault();
    if (!email.trim()) { setError('Enter your new email.'); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await startEmailChange(email.trim());
      if (!r.ok) { setError(r.error || 'That didn’t work. Try again.'); return; }
      setEmail(r.sent_to || email.trim());
      setCode('');
      setResendIn(r.resend_in ?? 30);
      setStep('code');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function check(e) {
    e?.preventDefault();
    if (code.length < 6) { setError('Enter all six digits.'); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await verifyEmailChange(code);
      if (r.expired) { setError('That code has expired. Send a new one.'); setCode(''); return; }
      if (!r.ok) { setError(r.error || 'That code didn’t match.'); return; }
      onDone(r.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const trail = [{ label: 'Profile', to: 'profile' },
                 { label: 'Sign-in and security', onClick: onBack }, { label: 'Email' }];
  if (step === 'code') {
    return (
      <div className="pk hm-page pf-page">
        <PageHead trail={trail} title="Check your email" onTab={onTab} />
        <p className="pf-intro">{`We sent a 6-digit code to ${email}. It works for 10 minutes.`}</p>
        <form className="pf-form pf-code" onSubmit={check}>
          <CodeInput value={code} onChange={(v) => { setCode(v); setError(null); }} error={!!error} />
          {error && <Alert tone="caution">{error}</Alert>}
          <PButton type="submit" disabled={busy}>{busy ? 'Checking…' : 'Change email'}</PButton>
          <PButton variant="text" disabled={busy || resendIn > 0} onClick={() => send()}>
            {resendIn > 0 ? `Send a new code in ${pad(resendIn)}` : 'Send a new code'}
          </PButton>
          <PButton variant="text" onClick={() => { setStep('email'); setError(null); }}>
            Use a different email
          </PButton>
        </form>
      </div>
    );
  }
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={trail} title="Change your sign-in email" onTab={onTab} />
      <form className="pf-form" onSubmit={send} noValidate>
        <Field label="Current email" id="sc-email-now">
          <input id="sc-email-now" type="email" value={user?.email || ''} readOnly
                 className="pf-readonly" />
        </Field>
        <Field label="New email" id="sc-email-new" error={error}>
          <input id="sc-email-new" type="email" autoComplete="email" value={email}
                 onChange={(e) => { setEmail(e.target.value); setError(null); }} />
          {!error && (
            <p className="gl-hint">We’ll send a 6-digit code to check it’s yours, and let your old email know.</p>
          )}
        </Field>
        <PButton type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send code'}</PButton>
        <PButton variant="text" onClick={onBack}>Cancel</PButton>
      </form>
    </div>
  );
}

export default function SecurityPanel({ onTab, onSignOut, version }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState('page');
  const [note, setNote] = useState(null);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [devices, setDevices] = useState([]);
  const [removing, setRemoving] = useState(false);
  const load = useCallback(() => Promise.all([
    getAuthStatus().then(setStatus),
    getDevices().then((d) => setDevices(d.devices ?? [])).catch(() => {}),
  ]).catch(setError), []);
  async function forget(d) {
    if (!window.confirm(`Remove ${d.label || 'this browser'}? It’s signed out, and won’t be asked to approve sign-ins.`)) return;
    setRemoving(true);
    setError(null);
    try {
      const r = await removeDevice(d.id);
      setDevices(r.devices ?? []);
      setNote(`${d.label || 'That browser'} removed.`);
    } catch (e) {
      setError(e);
    } finally {
      setRemoving(false);
    }
  }
  useEffect(() => { load(); }, [load, version]);
  useEffect(() => { if (view !== 'recovery') window.scrollTo?.(0, 0); }, [view]);
  const user = status?.user;

  async function addPasskey() {
    setPasskeyBusy(true);
    setError(null);
    try {
      await passkeyRegister(await createPasskey(await passkeyRegisterOptions()));
      setNote('Passkey added.');
      await load();
    } catch (e) {
      setError(e.name === 'NotAllowedError' ? new Error('The passkey prompt was closed.') : e);
    } finally {
      setPasskeyBusy(false);
    }
  }

  if (!status && error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!status) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading…</p></div>;

  if (view === 'email') {
    return (
      <ChangeEmail user={user} onTab={onTab} onBack={() => setView('page')}
                   onDone={async () => { setView('page'); setNote('Your sign-in email is changed.'); await load(); }} />
    );
  }
  return (
    <>
      {error && <div className="pk"><ErrorNote error={error} /></div>}
      <SecurityPage user={user} mail={status.mail} onTab={onTab}
                    onChangeEmail={() => setView('email')}
                    canPasskey={passkeysSupported()} onPasskey={addPasskey} passkeyBusy={passkeyBusy}
                    onRecovery={() => setView('recovery')} onSignOut={onSignOut}>
        <DevicesSection devices={devices} busy={removing} onRemove={forget} />
        {user?.has_password && <PasswordForm onDone={() => setNote('Password changed.')} />}
      </SecurityPage>
      {view === 'recovery' && (
        <RecoveryCodes had={user?.recovery_codes ?? 0} onMade={load}
                       onClose={() => setView('page')} />
      )}
      {note && <div className="pk"><Toast onDone={() => setNote(null)}>{note}</Toast></div>}
    </>
  );
}
