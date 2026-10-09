import { useEffect, useRef, useState } from 'react';
import {
  forgotPassword, login, passkeyOptions, passkeyRegister, passkeyRegisterOptions,
  passkeySignIn, resetPassword, startCode, verifyCode,
} from '../api.js';
import { DocSheet } from './docs.jsx';
import {
  AuthLayout, Banner, BigIcon, Callout, CodeInput, Field, Heading, TrustPoint,
} from './ui.jsx';
import { createPasskey, getPasskey, passkeysSupported } from './webauthn.js';

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

// Someone who has signed in on this device before starts at "Sign in", not
// at the welcome pitch.
const RETURNING = 'pearl-returning';
const remember = () => { try { localStorage.setItem(RETURNING, '1'); } catch { /* fine */ } };
const returning = () => { try { return localStorage.getItem(RETURNING) === '1'; } catch { return false; } };

const WELCOME_BACK = { mark: 'pearl', headline: 'Welcome back.',
                       body: 'Your money, sorted and up to date.' };

/**
 * Everything before you're signed in: the welcome (O-01), making an account
 * (O-02, O-03), and signing back in with a passkey or an email code
 * (A-01 to A-06, A-09, A-10). Accounts that still have a password can use it.
 */
export default function SignedOut({ onSignedIn }) {
  const resetToken = resetTokenFromUrl();
  const canPasskey = passkeysSupported();
  // Without passkeys in this browser, "sign in" means the email code.
  const pick = (s) => (s === 'signin' && !canPasskey ? 'email' : s);
  const [screen, setScreen] = useState(
    () => pick(resetToken ? 'reset' : returning() ? 'signin' : 'welcome'));
  const [history, setHistory] = useState([]);
  const [doc, setDoc] = useState(null);
  const [firstName, setFirstName] = useState('');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [resendIn, setResendIn] = useState(0);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);
  const [left, setLeft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [signedInUser, setSignedInUser] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState(null);
  const abort = useRef(null);

  useEffect(() => {
    if (resendIn <= 0) return undefined;
    const t = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [resendIn]);

  function show(next) {
    setHistory((h) => [...h, screen]);
    setScreen(pick(next));
    setError(null);
    setLeft(null);
  }
  function back() {
    abort.current?.abort();
    setHistory((h) => {
      const prev = h.at(-1) ?? 'welcome';
      setScreen(pick(prev));
      return h.slice(0, -1);
    });
    setError(null);
    setLeft(null);
    setBusy(false);
  }

  function finish(user, extra = {}) {
    remember();
    clearResetFromUrl();
    onSignedIn(user, extra);
  }

  async function sendCode(nextScreen) {
    setBusy(true);
    setError(null);
    try {
      const r = await startCode(email.trim(), firstName.trim(), creating);
      if (r.paused) { show('paused'); return false; }
      if (!r.ok) { setError(r.error || 'That didn’t work.'); return false; }
      setCode('');
      setLeft(null);
      setResendIn(r.resend_in ?? 30);
      if (nextScreen) show(nextScreen);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function checkCode(e) {
    e?.preventDefault();
    if (code.length < 6) { setError('Enter all six digits.'); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await verifyCode(email.trim(), code);
      if (r.paused) { show('paused'); return; }
      if (r.expired) { show('expired'); return; }
      if (!r.ok) { setError(r.error); setLeft(r.left ?? null); return; }
      // A returning account with no passkey on this device is offered one.
      if (!r.created && canPasskey && !(r.user?.passkeys > 0)) {
        setSignedInUser(r.user);
        remember();
        show('addPasskey');
        return;
      }
      finish(r.user, { created: r.created });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function signInWithPasskey() {
    show('waiting');
    const ctl = new AbortController();
    abort.current = ctl;
    try {
      const options = await passkeyOptions();
      const credential = await getPasskey(options, ctl.signal);
      const r = await passkeySignIn(credential);
      if (!r.ok) throw new Error(r.error);
      finish(r.user);
    } catch (e) {
      if (ctl.signal.aborted) return;
      setHistory((h) => h.slice(0, -1));
      setScreen('signin');
      setError(e.name === 'NotAllowedError'
        ? 'The passkey prompt was closed. Try again, or use an email code.'
        : (e.message || 'That passkey didn’t work here.'));
    }
  }

  async function addPasskey() {
    setBusy(true);
    setError(null);
    try {
      const options = await passkeyRegisterOptions();
      await passkeyRegister(await createPasskey(options));
      finish(signedInUser);
    } catch (e) {
      setError(e.name === 'NotAllowedError'
        ? 'The passkey prompt was closed. You can add one later.'
        : e.message);
    } finally {
      setBusy(false);
    }
  }

  async function attempt(fn) {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const r = await fn();
      if (!r.ok) { setError(r.error || 'That didn’t work.'); return; }
      if (r.signed_in) { setPassword(''); finish(r.user); return; }
      if (r.message) { setNote(r.message); show('sent'); }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const layout = (props, content) => (
    <>
      <AuthLayout onDoc={setDoc} {...props}>{content}</AuthLayout>
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)} />}
    </>
  );

  const newToPearl = (
    <>New to Pearl?{' '}
      <button type="button" className="p-link" onClick={() => {
        setCreating(true); show('details');
      }}>Create an account</button>
    </>
  );

  // ── O-01 Welcome ──────────────────────────────────────────────────────────
  if (screen === 'welcome') {
    return layout({
      mark: 'pearl', headline: 'Wealth grows in layers.',
      body: 'The shell opens as you do. Pearl starts with what’s safe to spend, then shows you the next step.',
    }, (
      <>
        <Heading title={<>Know what’s safe to spend.<br />Then grow from there.</>}
                 sub="Link your bank and Pearl does the sorting. Setup takes about 5 minutes." />
        <div className="p-points">
          <TrustPoint icon="eye" title="See what’s safe to spend">
            One number for what you can spend until payday.
          </TrustPoint>
          <TrustPoint icon="list" title="Spending, sorted for you">
            Every transaction categorized, with a quick way to fix any.
          </TrustPoint>
          <TrustPoint icon="trend" title="Your next step, always clear">
            Shell, then Glimmer, then Pearl. One step at a time.
          </TrustPoint>
        </div>
        <div className="p-actions">
          <button type="button" className="p-btn primary"
                  onClick={() => { setCreating(true); show('details'); }}>
            Get started
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => { setCreating(false); show('signin'); }}>
            I already have an account
          </button>
        </div>
      </>
    ));
  }

  // ── O-02 Name and email ───────────────────────────────────────────────────
  if (screen === 'details') {
    return layout({
      step: 1, headline: 'Let’s set you up.',
      body: 'About 5 minutes. You can stop any time and pick up where you left off.',
    }, (
      <form className="p-form" style={{ width: '100%' }} noValidate
            onSubmit={(e) => {
              e.preventDefault();
              if (!firstName.trim()) { setError('Tell us your first name.'); return; }
              sendCode('verify');
            }}>
        <Heading eyebrow="Create your account" title="Let’s start with you" />
        <Field label="First name">
          {(p) => <input {...p} type="text" autoComplete="given-name" value={firstName}
                         placeholder="Alex" required autoFocus
                         onChange={(e) => setFirstName(e.target.value)} />}
        </Field>
        <Field label="Email" hint="We’ll send a code to check it’s you." error={error}>
          {(p) => <input {...p} type="email" autoComplete="email" value={email}
                         placeholder="you@example.com" required
                         onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <div className="p-actions">
          <button className="p-btn primary" type="submit" disabled={busy}>
            {busy ? 'Sending…' : 'Continue'}
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => { setCreating(false); show('signin'); }}>
            Sign in instead
          </button>
        </div>
      </form>
    ));
  }

  // ── O-03 Verify email / A-04 Enter code / A-05 Wrong code ─────────────────
  if (screen === 'verify' || screen === 'code') {
    const signup = screen === 'verify';
    return layout(signup ? {
      step: 1, onBack: back, headline: 'Let’s set you up.',
      body: 'About 5 minutes. You can stop any time and pick up where you left off.',
    } : { ...WELCOME_BACK, onBack: back }, (
      <form className="p-form" style={{ width: '100%' }} onSubmit={checkCode}>
        <Heading eyebrow={signup ? 'Create your account' : 'Sign in with an email code'}
                 title={signup ? 'Check your email' : 'Enter your code'}
                 sub={signup
                   ? `We sent a 6-digit code to ${email.trim()}. It works for 10 minutes.`
                   : `We sent a 6-digit code to ${email.trim()}.`} />
        <div className="p-field">
          <CodeInput value={code} onChange={(v) => { setCode(v); setError(null); }}
                     error={!!error} />
          {error ? <p className="p-note caution" role="alert">{error}</p>
            : !signup && (resendIn > 0
              ? <p className="p-note">Send a new code in 0:{String(resendIn).padStart(2, '0')}</p>
              : <button type="button" className="p-link small" onClick={() => sendCode()}>
                  Send a new code
                </button>)}
          {signup && (
            <button type="button" className="p-link" onClick={back}>
              Use a different email
            </button>
          )}
        </div>
        <div className="p-actions">
          <button className="p-btn primary" type="submit" disabled={busy}>
            {busy ? 'Checking…' : signup ? 'Verify' : 'Sign in'}
          </button>
          {signup ? (
            <button type="button" className="p-btn text" disabled={busy || resendIn > 0}
                    onClick={() => sendCode()}>
              {resendIn > 0 ? `Send a new code in 0:${String(resendIn).padStart(2, '0')}`
                : 'Send a new code'}
            </button>
          ) : (
            <button type="button" className="p-btn text" onClick={back}>
              Use a different email
            </button>
          )}
        </div>
        {left != null && <span className="p-sr" aria-live="polite">{left} tries left</span>}
      </form>
    ));
  }

  // ── A-06 Code expired ─────────────────────────────────────────────────────
  if (screen === 'expired') {
    return layout({ ...WELCOME_BACK, onBack: back, centered: true }, (
      <>
        <BigIcon name="clock" />
        <Heading title="That code has expired"
                 sub="Codes work for 10 minutes. We can send you a new one." />
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={async () => {
                    if (!(await sendCode())) return;
                    setHistory((h) => h.slice(0, -1));
                    setScreen(creating ? 'verify' : 'code');
                  }}>
            Send a new code
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => { setHistory([]); setScreen(creating ? 'details' : 'email'); }}>
            Use a different email
          </button>
        </div>
      </>
    ));
  }

  // ── A-09 Short pause ──────────────────────────────────────────────────────
  if (screen === 'paused') {
    return layout({
      mark: 'closed', headline: 'Your account is safe.',
      body: 'Pausing sign-in is how we keep it that way.', centered: true,
    }, (
      <>
        <BigIcon name="clock" />
        <Heading title="Let’s take a short break"
                 sub="There were too many sign-in attempts, so we’ve paused sign-in for 15 minutes." />
        <Banner tone="positive">Your money is safe. Pearl can’t move money, and no one got in.</Banner>
        <div className="p-actions">
          <button type="button" className="p-btn primary" onClick={() => setDoc('help')}>
            Get help signing in
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => { setHistory([]); setScreen('welcome'); }}>
            Back to the start
          </button>
        </div>
      </>
    ));
  }

  // ── A-01 Sign in ──────────────────────────────────────────────────────────
  if (screen === 'signin') {
    return layout({ ...WELCOME_BACK, onBack: history.length ? back : undefined,
                    topRight: newToPearl }, (
      <>
        <Heading eyebrow="Welcome back" title="Sign in to Pearl"
                 sub="Use the passkey saved on this device." />
        <Callout title="Sign in with one tap">
          Face ID, Touch ID, Windows Hello or your device PIN.
        </Callout>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" onClick={signInWithPasskey}>
            Sign in with a passkey
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => { setCreating(false); show('email'); }}>
            Use an email code instead
          </button>
        </div>
        <p className="p-note">
          Can’t use your passkey? Use an email code, then add a new passkey.{' '}
          <button type="button" className="p-link small" onClick={() => show('password')}>
            Sign in with a password
          </button>
        </p>
      </>
    ));
  }

  // ── A-02 Waiting for passkey ──────────────────────────────────────────────
  if (screen === 'waiting') {
    return layout({ ...WELCOME_BACK, onBack: back, centered: true }, (
      <>
        <BigIcon name="fingerprint" />
        <Heading title="Waiting for your passkey"
                 sub="Follow the prompt from your browser to confirm it’s you." />
        <div className="p-actions">
          <button type="button" className="p-btn text" onClick={back}>Cancel</button>
        </div>
      </>
    ));
  }

  // ── A-03 Email code: enter email ──────────────────────────────────────────
  if (screen === 'email') {
    return layout({ ...WELCOME_BACK, onBack: history.length ? back : undefined,
                    topRight: newToPearl }, (
      <form className="p-form" style={{ width: '100%' }} noValidate
            onSubmit={(e) => { e.preventDefault(); sendCode('code'); }}>
        <Heading eyebrow="Sign in with an email code" title="What’s your email?" />
        <Field label="Email" error={error}
               hint="We’ll send a 6-digit code that works for 10 minutes.">
          {(p) => <input {...p} type="email" autoComplete="email" value={email}
                         placeholder="you@example.com" required autoFocus
                         onChange={(e) => setEmail(e.target.value)} />}
        </Field>
        <div className="p-actions">
          <button className="p-btn primary" type="submit" disabled={busy}>
            {busy ? 'Sending…' : 'Send code'}
          </button>
          {canPasskey && (
            <button type="button" className="p-btn text" onClick={() => show('signin')}>
              Use my passkey instead
            </button>
          )}
        </div>
      </form>
    ));
  }

  // ── A-10 Add a passkey to this device ─────────────────────────────────────
  if (screen === 'addPasskey') {
    return layout(WELCOME_BACK, (
      <>
        <Heading eyebrow="You’re signed in" title="Add a passkey to this device"
                 sub="Next time you can sign in with one tap." />
        <Callout title="Your browser will ask you to confirm">
          Your passkey stays on this device.
        </Callout>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy} onClick={addPasskey}>
            {busy ? 'Waiting…' : 'Create a passkey'}
          </button>
          <button type="button" className="p-btn text"
                  onClick={() => finish(signedInUser)}>
            Not now
          </button>
        </div>
      </>
    ));
  }

  // ── Accounts that still have a password ───────────────────────────────────
  const passwordScreens = {
    password: { title: 'Sign in with a password', eyebrow: 'Welcome back' },
    forgot: { title: 'Reset your password', eyebrow: 'Welcome back' },
    sent: { title: 'Check your email', eyebrow: 'Welcome back' },
    reset: { title: 'Choose a new password', eyebrow: 'Welcome back' },
  }[screen] ?? { title: 'Sign in', eyebrow: 'Welcome back' };

  return layout({ ...WELCOME_BACK, onBack: screen !== 'reset' ? back : undefined }, (
    <form className="p-form" style={{ width: '100%' }} onSubmit={(e) => {
      e.preventDefault();
      if (screen === 'password') attempt(() => login(username.trim(), password));
      else if (screen === 'forgot') attempt(() => forgotPassword(username.trim()));
      else if (screen === 'reset') attempt(() => resetPassword(resetToken, password));
    }}>
      <Heading eyebrow={passwordScreens.eyebrow} title={passwordScreens.title} />
      {screen === 'sent' && <p className="p-sub">{note}</p>}
      {(screen === 'password' || screen === 'forgot') && (
        <Field label={screen === 'forgot' ? 'Username or email' : 'Username'}>
          {(p) => <input {...p} type="text" value={username} autoFocus required
                         autoComplete="username" autoCapitalize="none" autoCorrect="off"
                         spellCheck={false} onChange={(e) => setUsername(e.target.value)} />}
        </Field>
      )}
      {(screen === 'password' || screen === 'reset') && (
        <Field label={screen === 'reset' ? 'New password' : 'Password'}>
          {(p) => <input {...p} type="password" value={password} required
                         autoFocus={screen === 'reset'}
                         minLength={screen === 'reset' ? 10 : undefined}
                         autoComplete={screen === 'reset' ? 'new-password' : 'current-password'}
                         onChange={(e) => setPassword(e.target.value)} />}
        </Field>
      )}
      {error && <Banner tone="caution">{error}</Banner>}
      {screen !== 'sent' && (
        <div className="p-actions">
          <button className="p-btn primary" type="submit" disabled={busy}>
            {busy ? 'One moment…' : { password: 'Sign in', forgot: 'Send reset link',
                                       reset: 'Save and sign in' }[screen]}
          </button>
          {screen === 'password' && (
            <button type="button" className="p-btn text" onClick={() => show('forgot')}>
              Forgot password?
            </button>
          )}
        </div>
      )}
    </form>
  ));
}
