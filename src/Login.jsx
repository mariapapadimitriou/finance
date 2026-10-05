import { useState } from 'react';
import Logo from './components/Logo.jsx';
import { login, signup } from './api.js';

/**
 * Sign in, or make an account.
 *
 * Each account has a ledger of its own, so a new one starts empty. On a
 * failed sign-in it shows exactly what the server said, which is the same
 * whether the username or the password was wrong.
 */
export default function Login({ onSignedIn }) {
  const [mode, setMode] = useState('in');            // 'in' | 'up'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const creating = mode === 'up';

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await (creating ? signup : login)(username.trim(), password);
      if (r.ok) {
        setPassword('');
        onSignedIn(r.user);
      } else {
        setError(r.error || "That username and password don't match.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="gate">
      <form className="card gate-card" onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 20 }}>
          <Logo size={38} />
          <div className="name">Spendie</div>
        </div>

        <label htmlFor="user" className="tile-label">Username</label>
        <input
          id="user"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          // eslint-disable-next-line jsx-a11y/no-autofocus
          autoFocus
          required
        />

        <label htmlFor="pw" className="tile-label">Password</label>
        <input
          id="pw"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={creating ? 'new-password' : 'current-password'}
          minLength={creating ? 10 : undefined}
          required
        />

        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? (creating ? 'Creating…' : 'Checking…')
            : (creating ? 'Create account' : 'Sign in')}
        </button>

        {error && (
          <div className="notice error" style={{ marginTop: 14 }}>{error}</div>
        )}

        <button type="button" className="btn quiet"
                onClick={() => { setMode(creating ? 'in' : 'up'); setError(null); }}>
          {creating ? 'I have an account' : 'Create an account'}
        </button>
      </form>
    </div>
  );
}
