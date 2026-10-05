import { useEffect, useState } from 'react';
import Logo from './components/Logo.jsx';
import {
  forgotPassword, getAuthStatus, login, resetPassword, signupWithEmail,
} from './api.js';

/** A reset link opens the app at /?reset=<token>. */
export function resetTokenFromUrl() {
  try {
    return new URLSearchParams(window.location.search).get('reset') || null;
  } catch {
    return null;
  }
}

function clearResetFromUrl() {
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete('reset');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  } catch { /* nothing to tidy */ }
}

/**
 * Sign in, make an account, or reset a forgotten password by email.
 *
 * A failed sign-in shows exactly what the server said, which is the same
 * whether the username or the password was wrong; "forgot" says the same
 * thing whether or not the account exists.
 */
export default function Login({ onSignedIn }) {
  const resetToken = resetTokenFromUrl();
  // 'in' | 'up' | 'forgot' | 'sent' | 'reset'
  const [mode, setMode] = useState(resetToken ? 'reset' : 'in');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mail, setMail] = useState(false);

  useEffect(() => {
    getAuthStatus().then((s) => setMail(!!s.mail)).catch(() => {});
  }, []);

  function show(next) {
    setMode(next);
    setError(null);
    setNote(null);
  }

  async function attempt(fn) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const r = await fn();
      if (!r.ok) {
        if (r.expired) show('in');
        setError(r.error || 'That didn’t work.');
        return;
      }
      if (r.signed_in) {
        setPassword('');
        clearResetFromUrl();
        onSignedIn(r.user);
        return;
      }
      if (r.message) {
        setNote(r.message);
        setMode('sent');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function submit(e) {
    e.preventDefault();
    if (mode === 'in') attempt(() => login(username.trim(), password));
    else if (mode === 'up') attempt(() => signupWithEmail(username.trim(), email.trim(), password));
    else if (mode === 'forgot') attempt(() => forgotPassword(username.trim()));
    else if (mode === 'reset') attempt(() => resetPassword(resetToken, password));
  }

  const title = {
    forgot: 'Reset your password',
    sent: 'Check your email',
    reset: 'Choose a new password',
  }[mode];

  return (
    <div className="gate">
      <form className="card gate-card" onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 20 }}>
          <Logo size={38} />
          <div className="name">Spendie</div>
        </div>
        {title && <h2 className="gate-title">{title}</h2>}

        {(mode === 'in' || mode === 'up') && (
          <>
            <label htmlFor="user" className="tile-label">Username</label>
            <input id="user" type="text" value={username}
                   onChange={(e) => setUsername(e.target.value)}
                   autoComplete="username" autoCapitalize="none" autoCorrect="off"
                   spellCheck={false}
                   // eslint-disable-next-line jsx-a11y/no-autofocus
                   autoFocus required />
          </>
        )}

        {mode === 'up' && (
          <>
            <label htmlFor="email" className="tile-label">Email</label>
            <input id="email" type="email" value={email}
                   onChange={(e) => setEmail(e.target.value)}
                   autoComplete="email" required={mail} />
          </>
        )}

        {(mode === 'in' || mode === 'up' || mode === 'reset') && (
          <>
            <label htmlFor="pw" className="tile-label">
              {mode === 'reset' ? 'New password' : 'Password'}
            </label>
            <input id="pw" type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)}
                   autoComplete={mode === 'in' ? 'current-password' : 'new-password'}
                   minLength={mode === 'in' ? undefined : 10}
                   // eslint-disable-next-line jsx-a11y/no-autofocus
                   autoFocus={mode === 'reset'} required />
          </>
        )}

        {mode === 'forgot' && (
          <>
            <label htmlFor="user" className="tile-label">Username or email</label>
            <input id="user" type="text" value={username}
                   onChange={(e) => setUsername(e.target.value)}
                   autoComplete="username" autoCapitalize="none" autoCorrect="off"
                   spellCheck={false}
                   // eslint-disable-next-line jsx-a11y/no-autofocus
                   autoFocus required />
          </>
        )}

        {mode === 'sent' && <p className="gate-note">{note}</p>}

        {mode !== 'sent' && (
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'One moment…' : {
              in: 'Sign in', up: 'Create account',
              forgot: 'Send reset link', reset: 'Save and sign in',
            }[mode]}
          </button>
        )}

        {error && <div className="notice error" style={{ marginTop: 14 }}>{error}</div>}

        {mode === 'in' && (
          <>
            <button type="button" className="btn quiet" onClick={() => show('forgot')}>
              Forgot password?
            </button>
            <button type="button" className="btn quiet" onClick={() => show('up')}>
              Create an account
            </button>
          </>
        )}
        {mode !== 'in' && (
          <button type="button" className="btn quiet"
                  onClick={() => { clearResetFromUrl(); show('in'); }}>
            Back to sign in
          </button>
        )}
      </form>
    </div>
  );
}
