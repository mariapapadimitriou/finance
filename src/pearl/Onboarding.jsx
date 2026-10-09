import { useEffect, useMemo, useState } from 'react';
import {
  createLinkToken, exchangePublicToken, getAccounts, getOnboarding, money,
  passkeyRegister, passkeyRegisterOptions, saveOnboarding,
} from '../api.js';
import { loadPlaidScript } from '../plaid.js';
import { DocSheet } from './docs.jsx';
import PIcon from './icons.jsx';
import {
  AuthLayout, Banner, Callout, Choice, Field, Heading, Initials, Lockup, MARKS, TrustPoint,
} from './ui.jsx';
import { createPasskey, passkeysSupported } from './webauthn.js';

// The banks most people here start with. Plaid's own window has every other.
const BANKS = [
  { name: 'RBC Royal Bank', short: 'RBC' }, { name: 'TD', short: 'TD' },
  { name: 'Scotiabank', short: 'S' }, { name: 'BMO', short: 'BMO' },
  { name: 'CIBC', short: 'CIBC' }, { name: 'Tangerine', short: 'T' },
  { name: 'Simplii', short: 'S' }, { name: 'EQ Bank', short: 'EQ' },
];

// The left panel for each step, as the design has it.
const PANEL = {
  passkey: { step: 2, headline: 'One tap to sign in.',
             body: 'No password to remember, and nothing for anyone to steal.' },
  province: { step: 3, headline: 'Built for Canada.',
              body: 'Pearl works with Canadian banks, accounts and tax-free savings.' },
  quebec: { mark: 'closed', headline: 'We’ll be there soon.',
            body: 'Pearl is coming to Quebec. We’ll let you know the moment it does.' },
  protect: { step: 4, headline: 'Your money stays yours.',
             body: 'Pearl can look, but it can never touch.' },
  consents: { step: 5, headline: 'You’re in control.',
              body: 'You can change the optional ones later in Settings.' },
  bank: { step: 6, headline: 'Start with the account your pay goes into.',
          body: 'You can add more banks later.' },
  syncing: { step: 6, headline: 'Almost there.', body: 'We’re bringing in your accounts.' },
  failed: { step: 6, headline: 'Nothing changed.',
            body: 'Your bank account is exactly as it was.' },
  linked: { step: 'done', headline: 'You’re all set.',
            body: 'Your accounts keep up to date on their own.' },
};

function screenFor(user, startAt) {
  const ob = user?.onboarding ?? {};
  if (startAt === 'passkey' && passkeysSupported() && !(user?.passkeys > 0)) return 'passkey';
  if (ob.province === 'QC') return 'quebec';
  return { protect: 'protect', consents: 'consents', bank: 'bank', linked: 'linked',
           path: 'path' }[ob.step] ?? 'province';
}

/**
 * Setting up a new account once it exists: a passkey (O-04), where you live
 * (O-05, with Quebec's waitlist O-05b), how Pearl protects you (O-06), your
 * choices (O-07), linking a bank through Plaid (O-08 to O-11), and a first
 * look at your path (O-12). Each step is saved, so leaving and coming back
 * resumes where you were.
 */
export default function Onboarding({ user: initialUser, startAt, onDone, onSignOut }) {
  const [user, setUser] = useState(initialUser);
  const [screen, setScreen] = useState(() => screenFor(initialUser, startAt));
  const [provinces, setProvinces] = useState(null);
  const [province, setProvince] = useState(initialUser?.onboarding?.province || '');
  const [consents, setConsents] = useState(() => {
    const c = initialUser?.onboarding?.consents ?? {};
    return { terms: !!c.terms?.value, read_data: !!c.read_data?.value,
             improve: !!c.improve?.value, tips: !!c.tips?.value };
  });
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [chosen, setChosen] = useState(null);
  const [bankName, setBankName] = useState('');
  const [phase, setPhase] = useState(0);
  const [itemId, setItemId] = useState(null);
  const [accounts, setAccounts] = useState(null);

  useEffect(() => {
    getOnboarding().then((r) => setProvinces(r.provinces)).catch(() => {});
  }, []);

  useEffect(() => {
    if (screen !== 'linked') return;
    getAccounts().then((r) => {
      const linked = (r.accounts ?? []).filter((a) => (itemId ? a.item_id === itemId : !!a.item_id));
      setAccounts(linked);
    }).catch((e) => setError(e.message));
  }, [screen, itemId]);

  async function save(fields, next) {
    setBusy(true);
    setError(null);
    try {
      const r = await saveOnboarding(fields);
      setUser(r.user);
      if (next) setScreen(next);
      return r.user;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function addPasskey() {
    setBusy(true);
    setError(null);
    try {
      const options = await passkeyRegisterOptions();
      const r = await passkeyRegister(await createPasskey(options));
      setUser(r.user);
      setScreen('province');
    } catch (e) {
      setError(e.name === 'NotAllowedError'
        ? 'The passkey prompt was closed. Try again, or use email codes for now.'
        : e.message);
    } finally {
      setBusy(false);
    }
  }

  async function link() {
    setBusy(true);
    setError(null);
    try {
      const [Plaid, { link_token: token }] = await Promise.all([
        loadPlaidScript(), createLinkToken(),
      ]);
      const handler = Plaid.create({
        token,
        onSuccess: async (publicToken, metadata) => {
          setBusy(false);
          const name = metadata?.institution?.name || chosen || 'your bank';
          setBankName(name);
          setPhase(1);
          setScreen('syncing');
          try {
            const r = await exchangePublicToken(publicToken, metadata?.institution?.name || '');
            setItemId(r.item_id ?? null);
            setPhase(2);
            await new Promise((ok) => { setTimeout(ok, 700); });
            setPhase(3);
            await saveOnboarding({ step: 'linked' }).then((s) => setUser(s.user)).catch(() => {});
            setScreen('linked');
          } catch (e) {
            setError(e.message);
            setScreen('failed');
          }
        },
        onExit: (err, metadata) => {
          setBusy(false);
          // Closing Plaid's window on purpose isn't a failure.
          if (err) {
            setBankName(metadata?.institution?.name || chosen || 'Your bank');
            setError(err.display_message || err.error_message || null);
            setScreen('failed');
          }
        },
      });
      handler.open();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  const shownBanks = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? BANKS.filter((b) => b.name.toLowerCase().includes(q)) : BANKS;
  }, [search]);

  const layout = (key, props, content) => (
    <>
      <AuthLayout onDoc={setDoc} {...PANEL[key]} {...props}>{content}</AuthLayout>
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)}
                        backLabel={screen === 'protect' ? 'How we protect you' : undefined} />}
    </>
  );
  const signOut = onSignOut && (
    <button type="button" className="p-link small" onClick={onSignOut}>Sign out</button>
  );

  // ── O-04 Create a passkey ─────────────────────────────────────────────────
  if (screen === 'passkey') {
    return layout('passkey', {}, (
      <>
        <Heading eyebrow="Create your account" title="Sign in faster with a passkey"
                 sub="Use your face, fingerprint or device PIN instead of a password." />
        <Callout title="Your browser will ask you to confirm">
          Face ID, Touch ID, Windows Hello or your device PIN. Your passkey stays on your device.
        </Callout>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy} onClick={addPasskey}>
            {busy ? 'Waiting…' : 'Create a passkey'}
          </button>
          <button type="button" className="p-btn text" onClick={() => setScreen('province')}>
            Not now, use email codes
          </button>
        </div>
      </>
    ));
  }

  // ── O-05 Province ─────────────────────────────────────────────────────────
  if (screen === 'province') {
    return layout('province', { topRight: <>Step 3 of 6 · {signOut}</> }, (
      <form className="p-form" style={{ width: '100%' }} onSubmit={(e) => {
        e.preventDefault();
        if (!province) { setError('Choose a province or territory.'); return; }
        save({ province }, province === 'QC' ? 'quebec' : 'protect');
      }}>
        <Heading eyebrow="About you" title="Where do you live?"
                 sub="Some features depend on your province or territory." />
        <Field label="Province or territory" icon="pin" error={error}
               hint="Pearl isn’t available in Quebec yet.">
          {(p) => (
            <>
              <select {...p} value={province} required
                      onChange={(e) => { setProvince(e.target.value); setError(null); }}>
                <option value="" disabled>Choose one</option>
                {Object.entries(provinces ?? {}).sort((a, b) => a[1].localeCompare(b[1]))
                  .map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
              <PIcon name="chevronDown" className="p-chevron" />
            </>
          )}
        </Field>
        <div className="p-actions">
          <button className="p-btn primary" type="submit" disabled={busy || !provinces}>
            Continue
          </button>
        </div>
      </form>
    ));
  }

  // ── O-05b Quebec waitlist ─────────────────────────────────────────────────
  if (screen === 'quebec') {
    const joined = user?.onboarding?.waitlist;
    return layout('quebec', { onBack: () => setScreen('province'), centered: true,
                              topRight: signOut }, (
      <>
        <img src={MARKS.opening} alt="" width="96" height="80" />
        <Heading title="Pearl isn’t in Quebec yet"
                 sub={`We’re working on it. We’ll email ${user?.email ?? 'you'} as soon as Pearl is available in Quebec.`} />
        {joined
          ? <Banner tone="positive">You’re on the waitlist. We’ll email you when Pearl arrives.</Banner>
          : <Banner tone="info">We won’t link a bank or keep any financial data in the meantime.</Banner>}
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy || joined}
                  onClick={() => save({ waitlist: true })}>
            {joined ? 'You’re on the waitlist' : 'Join the waitlist'}
          </button>
          <button type="button" className="p-btn text" onClick={() => setScreen('province')}>
            I chose the wrong province
          </button>
        </div>
      </>
    ));
  }

  // ── O-06 How we protect you ───────────────────────────────────────────────
  if (screen === 'protect') {
    return layout('protect', { onBack: () => setScreen('province') }, (
      <>
        <Heading eyebrow="Before you link" title="How we protect you"
                 sub="Here’s exactly what Pearl can and can’t do with your bank." />
        <div className="p-points">
          <TrustPoint icon="eye" title="Read-only access">
            Pearl can see your balances and transactions. That’s all.
          </TrustPoint>
          <TrustPoint icon="ban" title="Pearl can’t move money">
            No payments, transfers or withdrawals, ever.
          </TrustPoint>
          <TrustPoint icon="key" title="We never see your bank password"
                      link="How signing in through Plaid works" onLink={() => setDoc('plaid')}>
            You sign in to your bank through Plaid. Your login goes to your bank, not to us.
          </TrustPoint>
          <TrustPoint icon="database" title="What we store"
                      link="See everything we store" onLink={() => setDoc('store')}>
            Account names, balances and transactions, encrypted.
          </TrustPoint>
          <TrustPoint icon="users" title="Who we share with"
                      link="See who we share with" onLink={() => setDoc('share')}>
            We don’t sell your data. We share only what’s needed to run Pearl.
          </TrustPoint>
        </div>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => save({ step: 'consents' }, 'consents')}>
            Continue
          </button>
        </div>
      </>
    ));
  }

  // ── O-07 Consents ─────────────────────────────────────────────────────────
  if (screen === 'consents') {
    const set = (k) => (v) => { setConsents((c) => ({ ...c, [k]: v })); setError(null); };
    return layout('consents', { onBack: () => setScreen('protect') }, (
      <>
        <Heading eyebrow="Before you link" title="Your choices"
                 sub="Two agreements are needed to link a bank. The rest is up to you." />
        <div className="p-choices">
          <Choice checked={consents.terms} onChange={set('terms')} description="Required"
                  label={<>I agree to the{' '}
                    <button type="button" className="p-link"
                            onClick={(e) => { e.preventDefault(); setDoc('terms'); }}>Terms</button>
                    {' '}and the{' '}
                    <button type="button" className="p-link"
                            onClick={(e) => { e.preventDefault(); setDoc('privacy'); }}>Privacy policy</button>
                  </>} />
          <Choice checked={consents.read_data} onChange={set('read_data')} description="Required"
                  label="Pearl can read my balances and transactions to build my budget" />
          <Choice checked={consents.improve} onChange={set('improve')} description="Optional"
                  label="Use my categorized transactions to improve suggestions" />
          <Choice checked={consents.tips} onChange={set('tips')} description="Optional"
                  label="Send me tips and product news by email" />
        </div>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => {
                    if (!consents.terms || !consents.read_data) {
                      setError('Both required agreements are needed to link a bank.');
                      return;
                    }
                    save({ consents }, 'bank');
                  }}>
            Agree and continue
          </button>
        </div>
      </>
    ));
  }

  // ── O-08 Choose your bank (O-09 is Plaid's own window) ────────────────────
  if (screen === 'bank') {
    return layout('bank', { onBack: () => setScreen('consents') }, (
      <>
        <Heading eyebrow="Link your accounts" title="Link your main bank"
                 sub="Pick your bank to continue. You’ll sign in to it through Plaid." />
        <Field label="Find your bank" icon="search">
          {(p) => <input {...p} type="search" value={search}
                         placeholder="Search banks and credit unions"
                         onChange={(e) => setSearch(e.target.value)} />}
        </Field>
        {shownBanks.length > 0 ? (
          <div className="p-tiles" role="radiogroup" aria-label="Popular banks">
            {shownBanks.map((b) => (
              <button key={b.name} type="button" role="radio" aria-checked={chosen === b.name}
                      className={`p-tile${chosen === b.name ? ' on' : ''}`}
                      onClick={() => setChosen(chosen === b.name ? null : b.name)}>
                <span className="p-initials" aria-hidden="true">{b.short}</span>
                <span>{b.name}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="p-note">Not in this list? Continue — Plaid can find thousands more
            banks and credit unions.</p>
        )}
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy} onClick={link}>
            {busy ? 'Opening Plaid…' : 'Continue with Plaid'}
          </button>
        </div>
        <p className="p-note">
          Plaid, our connection partner, opens in a secure window. You sign in to your bank
          there, not in Pearl.
        </p>
      </>
    ));
  }

  // ── O-10 Return and sync ──────────────────────────────────────────────────
  if (screen === 'syncing') {
    const rows = [
      { label: `Signed in to ${bankName}`, icon: 'check' },
      { label: 'Finding your accounts', icon: 'refresh' },
      { label: 'Getting recent transactions', icon: 'refresh' },
    ];
    return layout('syncing', {}, (
      <>
        <Heading eyebrow="Link your accounts" title={`Connecting to ${bankName}`}
                 sub="This usually takes under a minute." />
        <div className="p-progress" role="progressbar" aria-valuemin={0} aria-valuemax={3}
             aria-valuenow={phase} aria-label="Linking progress">
          <div style={{ width: `${Math.max(phase, 0.5) / 3 * 100}%` }} />
        </div>
        <ul className="p-checks" aria-live="polite">
          {rows.map((r, i) => {
            const state = i < phase ? 'done' : i === phase ? 'active' : '';
            return (
              <li key={r.label} className={state}>
                <span aria-hidden="true">
                  <PIcon name={state === 'done' ? 'check' : state === 'active' ? r.icon : 'clock'} />
                </span>
                <span>{r.label}</span>
              </li>
            );
          })}
        </ul>
        <p className="p-note">Keep this page open. It’s nearly done.</p>
      </>
    ));
  }

  // ── O-10b Couldn't finish linking ─────────────────────────────────────────
  if (screen === 'failed') {
    return layout('failed', {}, (
      <>
        <Heading eyebrow="Link your accounts" title="We couldn’t finish linking"
                 sub={`${bankName || 'Your bank'} didn’t finish connecting. Nothing changed in your bank account, and Pearl didn’t save anything.`} />
        <Banner tone="caution">
          {error || 'This is usually temporary. Trying again in a minute often works.'}
        </Banner>
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => { setError(null); link(); }}>
            Try again
          </button>
          <button type="button" className="p-btn secondary"
                  onClick={() => { setError(null); setChosen(null); setScreen('bank'); }}>
            Choose a different bank
          </button>
        </div>
      </>
    ));
  }

  // ── O-11 Accounts linked ──────────────────────────────────────────────────
  if (screen === 'linked') {
    const bank = bankName || accounts?.[0]?.institution || 'your bank';
    const n = accounts?.length ?? 0;
    return layout('linked', {}, (
      <>
        <Heading eyebrow="All set" title="You’re connected"
                 sub={accounts == null ? 'Getting your accounts…'
                   : `We found ${n} account${n === 1 ? '' : 's'} at ${bank}.`} />
        <div className="p-accounts">
          {(accounts ?? []).map((a) => <AccountRow key={a.account_id} a={a} />)}
        </div>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => save({ step: 'path' }, 'path')}>
            See your path
          </button>
          <button type="button" className="p-btn secondary"
                  onClick={() => { setChosen(null); setItemId(null); setScreen('bank'); }}>
            Add another bank
          </button>
        </div>
      </>
    ));
  }

  // ── O-12 First look at your path ──────────────────────────────────────────
  const finish = async (dest) => {
    await save({ done: true });
    onDone?.(dest);
  };
  return (
    <div className="pearl">
      <main className="p-path">
        <Lockup />
        <Heading eyebrow="Your path" title="Here’s where you’re starting"
                 sub="Pearl grows in three phases. You’re in Shell: cover the basics." />
        <div className="p-phases">
          <div className="p-phase current" aria-current="step">
            <img src={MARKS.closed} alt="" />
            <h2 className="p-h3">Shell</h2>
            <small>Cover the basics</small>
            <p className="p-eyebrow">You are here</p>
          </div>
          <div className="p-phase upcoming">
            <img src={MARKS.opening} alt="" />
            <h2 className="p-h3">Glimmer</h2>
            <small>Build your safety net</small>
          </div>
          <div className="p-phase upcoming">
            <img src={MARKS.pearl} alt="" />
            <h2 className="p-h3">Pearl</h2>
            <small>Ready to invest</small>
          </div>
        </div>
        <h2 className="p-h3">Next in Shell</h2>
        <div className="p-next">
          {[
            { icon: 'eye', title: 'Check your safe-to-spend',
              sub: 'See what you can spend until payday', dest: 'today' },
            { icon: 'list', title: 'Review a few transactions',
              sub: 'Fix anything Pearl sorted wrong', dest: 'transactions' },
            { icon: 'target', title: 'Set up your safety net',
              sub: 'Pick a starter amount to save', dest: 'plan' },
          ].map((r) => (
            <button key={r.title} type="button" disabled={busy} onClick={() => finish(r.dest)}>
              <span className="p-bubble" aria-hidden="true"><PIcon name={r.icon} /></span>
              <span className="grow">{r.title}<small>{r.sub}</small></span>
              <PIcon name="chevronRight" />
            </button>
          ))}
        </div>
        {error && <Banner tone="caution">{error}</Banner>}
        <button type="button" className="p-btn primary" disabled={busy}
                onClick={() => finish('today')}>
          Go to Home
        </button>
      </main>
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)} />}
    </div>
  );
}

function AccountRow({ a }) {
  const b = a.balance;
  const credit = a.plaid_type === 'credit';
  const amount = b?.current == null ? null
    : credit ? `${money(b.current, { cents: true })} owing` : money(b.current, { cents: true });
  const meta = [a.mask ? `••${a.mask}` : null, amount].filter(Boolean).join(' · ');
  const name = a.institution ? `${a.institution} ${a.kind_label ?? ''}`.trim()
    : (a.account_name || a.account_id);
  return (
    <div className="p-account">
      <Initials name={a.institution || name} large />
      <div className="p-account-text">
        <span>{name}</span>
        {meta && <small>{meta}</small>}
      </div>
      <span className="p-chip"><PIcon name="check" /> Synced</span>
    </div>
  );
}
