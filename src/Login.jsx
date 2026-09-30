import { useState } from 'react';
import Logo from './components/Logo.jsx';
import { login } from './api.js';

/**
 * The password screen.
 *
 * One field, because there is one person and one secret — no accounts, no
 * signup, no reset link to get wrong. It says as little as possible about a
 * failure: the server returns the same message whatever was wrong with the
 * guess, and this shows exactly that rather than inventing a more helpful one.
 */
export default function Login({ onSignedIn }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await login(password);
      if (r.ok) {
        setPassword('');
        onSignedIn();
      } else {
        setError(r.error || "That password isn't right.");
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

        <label htmlFor="pw" className="tile-label">Password</label>
        <input
          id="pw"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete="current-password"
          // eslint-disable-next-line jsx-a11y/no-autofocus
          required
        />

        <button className="btn primary" type="submit" disabled={busy}
                style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>

        {error && (
          <div className="notice error" style={{ marginTop: 14 }}>{error}</div>
        )}

        <p className="small muted" style={{ marginTop: 18, marginBottom: 0 }}>
          Your spending — and the banks you&apos;ve connected — are behind this.
        </p>
      </form>
    </div>
  );
}
