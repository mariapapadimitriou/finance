import { useEffect, useState } from 'react';
import { Card, ErrorNote, Notice } from '../components/ui.jsx';
import { changePassword, getAuthStatus } from '../api.js';

/** Who is signed in, a new password, and signing out. */
export default function AccountPanel({ onSignOut }) {
  const [user, setUser] = useState(null);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    getAuthStatus().then((s) => setUser(s.user)).catch(() => {});
  }, []);

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
    <div className="stack">
      <Card title={user ? user.username : 'Account'}
            actions={onSignOut && (
              <button className="btn quiet" onClick={onSignOut}>Sign out</button>
            )}>
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
      </Card>
    </div>
  );
}
