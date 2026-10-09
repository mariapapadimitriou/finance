import { useEffect, useState } from 'react';
import { Card, ErrorNote, Notice } from '../components/ui.jsx';
import {
  changeEmail, changePassword, getAuthStatus, passkeyRegister, passkeyRegisterOptions,
  saveOnboarding,
} from '../api.js';
import { createPasskey, passkeysSupported } from '../pearl/webauthn.js';

/** Who is signed in, their email, passkeys, a password if they have one, the
 *  optional choices from setup, and signing out. */
export default function AccountPanel({ onSignOut }) {
  const [status, setStatus] = useState(null);

  const load = () => getAuthStatus().then(setStatus).catch(() => {});
  useEffect(() => { load(); }, []);

  const user = status?.user;

  return (
    <div className="stack">
      <Card title={user ? (user.first_name || user.username) : 'Account'}
            actions={onSignOut && (
              <button className="btn quiet" onClick={onSignOut}>Sign out</button>
            )}>
        <EmailForm user={user} mail={status?.mail} onSaved={load} />
      </Card>
      {user && <PasskeyCard user={user} onSaved={load} />}
      {user?.has_password !== false && (
        <Card title="Password">
          <PasswordForm />
        </Card>
      )}
      {user?.onboarding?.consents?.terms && <ChoicesCard user={user} onSaved={load} />}
    </div>
  );
}

/** Sign in with Face ID, Touch ID, Windows Hello or a PIN on this device. */
function PasskeyCard({ user, onSaved }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const n = user.passkeys ?? 0;
  async function add() {
    setBusy(true); setError(null); setDone(false);
    try {
      await passkeyRegister(await createPasskey(await passkeyRegisterOptions()));
      setDone(true);
      onSaved();
    } catch (e) {
      setError(e.name === 'NotAllowedError' ? new Error('The passkey prompt was closed.') : e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="Passkeys">
      <p className="muted" style={{ marginTop: 0 }}>
        {n === 0 ? 'None yet. You sign in with a code sent to your email.'
          : `${n} saved. Sign in with one tap on ${n === 1 ? 'that device' : 'those devices'}.`}
      </p>
      {passkeysSupported() && (
        <button className="btn" disabled={busy} onClick={add}>
          {busy ? 'Waiting…' : 'Add a passkey on this device'}
        </button>
      )}
      {done && <Notice kind="good">Passkey added</Notice>}
      <ErrorNote error={error} />
    </Card>
  );
}

/** The two optional choices from setup; the required two stay agreed. */
function ChoicesCard({ user, onSaved }) {
  const c = user.onboarding.consents;
  const [error, setError] = useState(null);
  async function set(key, value) {
    setError(null);
    try {
      await saveOnboarding({ consents: {
        terms: true, read_data: true,
        improve: key === 'improve' ? value : !!c.improve?.value,
        tips: key === 'tips' ? value : !!c.tips?.value,
      } });
      onSaved();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Card title="Your choices">
      <label className="row" style={{ gap: 8 }}>
        <input type="checkbox" checked={!!c.improve?.value}
               onChange={(e) => set('improve', e.target.checked)} />
        Use my categorized transactions to improve suggestions
      </label>
      <label className="row" style={{ gap: 8, marginTop: 8 }}>
        <input type="checkbox" checked={!!c.tips?.value}
               onChange={(e) => set('tips', e.target.checked)} />
        Send me tips and product news by email
      </label>
      <ErrorNote error={error} />
    </Card>
  );
}

/** Where a reset link goes if the password is ever forgotten. */
function EmailForm({ user, mail, onSaved }) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const r = await changeEmail(email.trim());
      if (!r.ok) throw new Error(r.error || 'That didn\u2019t work.');
      setEmail('');
      setDone(true);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <span className="tile-label" style={{ margin: 0 }}>Email</span>
        <strong>{user?.email || 'None yet'}</strong>
      </div>
      {mail === false && (
        <Notice>Email isn&apos;t set up on this deployment yet</Notice>
      )}
      <form className="controls" onSubmit={save}>
        <label htmlFor="email-new">{user?.email ? 'New email' : 'Add an email'}</label>
        <input id="email-new" type="email" autoComplete="email" value={email}
               onChange={(e) => setEmail(e.target.value)} required
               style={{ width: 240 }} />
        <button className="btn" type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
      <ErrorNote error={error} />
      {done && <Notice kind="good">Email saved</Notice>}
    </div>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const r = await changePassword(current, next);
      if (!r.ok) throw new Error(r.error || 'That didn’t work.');
      setCurrent('');
      setNext('');
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="controls" onSubmit={save}>
        <label htmlFor="pw-current">Current password</label>
        <input id="pw-current" type="password" autoComplete="current-password"
               value={current} onChange={(e) => setCurrent(e.target.value)}
               required style={{ width: 200 }} />
        <label htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" autoComplete="new-password"
               minLength={10} value={next} onChange={(e) => setNext(e.target.value)}
               required style={{ width: 200 }} />
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Change password'}
        </button>
      </form>
      <ErrorNote error={error} />
      {done && <Notice kind="good">Password changed</Notice>}
    </>
  );
}
