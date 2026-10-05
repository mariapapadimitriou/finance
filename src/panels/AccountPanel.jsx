import { useEffect, useState } from 'react';
import { Card, ErrorNote, Notice } from '../components/ui.jsx';
import { changeEmail, changePassword, getAuthStatus } from '../api.js';

/** Who is signed in, their email, a new password, and signing out. */
export default function AccountPanel({ onSignOut }) {
  const [status, setStatus] = useState(null);

  const load = () => getAuthStatus().then(setStatus).catch(() => {});
  useEffect(() => { load(); }, []);

  const user = status?.user;

  return (
    <div className="stack">
      <Card title={user ? user.username : 'Account'}
            actions={onSignOut && (
              <button className="btn quiet" onClick={onSignOut}>Sign out</button>
            )}>
        <EmailForm user={user} mail={status?.mail} onSaved={load} />
      </Card>
      <Card title="Password">
        <PasswordForm />
      </Card>
    </div>
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
