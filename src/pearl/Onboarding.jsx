import { useEffect, useMemo, useState } from 'react';
import {
  createLinkToken, exchangePublicToken, getAccounts, getAccountsOverview, getOnboarding, money,
  passkeyRegister, passkeyRegisterOptions, saveAccountSettings, saveOnboarding,
} from '../api.js';
import { SharedAccountsForm, shareable } from '../panels/SetupAgain.jsx';
import { loadPlaidScript } from '../plaid.js';
import { DocSheet } from './docs.jsx';
import IncomeBillsFlow from './IncomeBills.jsx';
import PIcon from './icons.jsx';
import { LINKING, ProtectPoints, Rows, TIPS, USES } from './privacy.jsx';
import {
  AuthLayout, Banner, Callout, Choice, Field, Heading, Initials, MARKS,
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
              body: 'Change your mind any time in Profile › Privacy and consent.' },
  uses: { headline: 'Your numbers, your call.', body: 'Pearl only uses your transactions for you.',
          footnote: false },
  email: { headline: 'You’re in control.',
           body: 'Change this any time in Profile › Privacy and consent.', footnote: false },
  bank: { step: 6, headline: 'Start with the account your pay goes into.',
          body: 'You can add more banks later.' },
  syncing: { step: 6, headline: 'Almost there.', body: 'We’re bringing in your accounts.' },
  failed: { step: 6, headline: 'Nothing changed.',
            body: 'Your bank account is exactly as it was.' },
  linked: { step: 'done', headline: 'You’re all set.',
            body: 'Your accounts keep up to date on their own.' },
  shared: { headline: 'Only your share counts.',
            body: 'On an account you share, Pearl counts your part and asks who put money in.' },
};

function screenFor(user, startAt) {
  const ob = user?.onboarding ?? {};
  if (startAt === 'passkey' && passkeysSupported() && !(user?.passkeys > 0)) return 'passkey';
  if (ob.province === 'QC') return 'quebec';
  return { protect: 'protect', consents: 'consents', bank: 'bank', linked: 'linked',
           shared: 'shared', uses: 'uses', income: 'income', email: 'email', path: 'email' }[ob.step] ?? 'province';
}

/**
 * Setting up a new account once it exists: a passkey (O-04), where you live
 * (O-05, with Quebec's waitlist O-05b), how Pearl protects you (O-06, THL-115
 * T-01), linking your bank (THL-117 CN-01, which replaced O-07's checkboxes),
 * linking through Plaid (O-08 to O-11), how Pearl uses your transactions
 * (CN-02), confirming income and regular bills (THL-127 I-01 to I-06,
 * IncomeBills.jsx), one last thing (CN-03, tips by email) and a first look at
 * your path (O-12): where you start (THL-130 GR-06, GR-07, or GR-10 with an
 * investment account already linked). Each step is saved, so leaving and coming back resumes
 * where you were. The consent moments share their words with Profile ›
 * Privacy and consent (privacy.jsx).
 */
export default function Onboarding({ user: initialUser, startAt, onDone, onSignOut }) {
  const [user, setUser] = useState(initialUser);
  const [screen, setScreen] = useState(() => screenFor(initialUser, startAt));
  const [provinces, setProvinces] = useState(null);
  const [province, setProvince] = useState(initialUser?.onboarding?.province || '');
  // CN-02's AI choice starts unchosen; CN-03's box starts unticked.
  const [ai, setAi] = useState(() => {
    const c = initialUser?.onboarding?.consents?.ai_sort;
    return c ? (c.value ? 'yes' : 'no') : null;
  });
  const [tips, setTips] = useState(!!initialUser?.onboarding?.consents?.tips?.value);
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

  // CN-03's Finish (2026-10-21): the path's "First look" (O-12) went with
  // Wins, so the last answer saves and the app opens on Home.
  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveOnboarding({ consents: { tips }, done: true });
      onDone?.('home');
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

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
        <ProtectPoints onDoc={setDoc} />
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

  // ── CN-01 Linking your bank (replaces O-07) ───────────────────────────────
  if (screen === 'consents') {
    const openDoc = (name) => (e) => { e.preventDefault(); setDoc(name); };
    return layout('consents', { onBack: () => setScreen('protect') }, (
      <>
        <Heading eyebrow={LINKING.eyebrow} title={LINKING.title} sub={LINKING.sub} />
        <Rows rows={LINKING.rows} label="What linking means" />
        <p className="p-small">
          By continuing, you agree to the{' '}
          <button type="button" className="p-link small" onClick={openDoc('terms')}>Terms</button>
          {' '}and{' '}
          <button type="button" className="p-link small" onClick={openDoc('privacy')}>Privacy policy</button>
          , and that Pearl can read the accounts you link.
        </p>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => save({ consents: { terms: true, read_data: true } }, 'bank')}>
            {LINKING.agree}
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
                  onClick={() => save({ step: 'shared' }, 'shared')}>
            Continue
          </button>
          <button type="button" className="p-btn secondary"
                  onClick={() => { setChosen(null); setItemId(null); setScreen('bank'); }}>
            Add another bank
          </button>
        </div>
      </>
    ));
  }

  // ── Which accounts do you share? (2026-10-29) ───────────────────────────
  // Right after linking, so a joint account counts only her share from the
  // start. Start over asks it again (SetupAgain.jsx).
  if (screen === 'shared') {
    return (
      <SharedStep busy={busy} error={error} onBack={() => setScreen('linked')}
                  layout={(content) => layout('shared', { onBack: () => setScreen('linked') }, content)}
                  onDone={async (changes) => {
                    setBusy(true);
                    setError(null);
                    try {
                      for (const [id, fields] of changes) await saveAccountSettings(id, fields);
                    } catch (e) {
                      setError(e.message);
                      setBusy(false);
                      return;
                    }
                    setBusy(false);
                    save({ step: 'uses' }, 'uses');
                  }} />
    );
  }

  // ── CN-02 How Pearl uses your transactions (after linking) ────────────────
  if (screen === 'uses') {
    const choose = (v) => () => { setAi(v); setError(null); };
    return layout('uses', {}, (
      <>
        <Heading eyebrow={USES.eyebrow} title={USES.title} />
        <section className="p-uses">
          <h2 className="p-h3">{USES.needTitle}</h2>
          <p>{USES.need}</p>
        </section>
        <section className="p-uses">
          <h2 className="p-h3">{USES.aiTitle}</h2>
          <p>{USES.ai}</p>
        </section>
        <div className="p-choices" role="radiogroup" aria-label="Sort with AI">
          <Choice type="radio" name="ai" checked={ai === 'yes'} onChange={choose('yes')}
                  label={USES.yes.label} description={USES.yes.description} />
          <Choice type="radio" name="ai" checked={ai === 'no'} onChange={choose('no')}
                  label={USES.no.label} description={USES.no.description} />
        </div>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={() => {
                    if (!ai) { setError('Choose yes or no to continue.'); return; }
                    save({ consents: { insights: true, ai_sort: ai === 'yes' }, step: 'income' },
                         'income');
                  }}>
            Continue
          </button>
        </div>
      </>
    ));
  }

  // ── CN-03 One last thing ──────────────────────────────────────────────────
  if (screen === 'email') {
    return layout('email', {}, (
      <>
        <Heading eyebrow={TIPS.eyebrow} title={TIPS.title} />
        <div className="p-choices">
          <Choice checked={tips} onChange={setTips} label={TIPS.label}
                  description={TIPS.description} />
        </div>
        <p className="p-small">{TIPS.foot}</p>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy}
                  onClick={finish}>
            Finish
          </button>
        </div>
      </>
    ));
  }

  // ── I-01 to I-06 Income and recurring bills (THL-127) ─────────────────────
  if (screen === 'income') {
    return (
      <>
        <IncomeBillsFlow onDoc={setDoc} onDone={() => save({ step: 'email' }, 'email')} />
        {doc && <DocSheet name={doc} onClose={() => setDoc(null)} />}
      </>
    );
  }

  return null;
}

/** "Do you share any of these accounts?", in setup's layout. */
function SharedStep({ layout, busy, error, onDone }) {
  const [accounts, setAccounts] = useState(null);
  const [failed, setFailed] = useState(null);
  useEffect(() => {
    getAccountsOverview().then((o) => setAccounts(shareable(o.linked ?? [])))
      .catch((e) => setFailed(e.message));
  }, []);
  return layout(
    <>
      <Heading eyebrow="One more thing" title="Do you share any of these accounts?"
               sub="With a partner, a sibling or a roommate. Change it any time in Profile › Accounts." />
      {failed && <Banner tone="caution">{failed}</Banner>}
      {accounts == null && !failed && <p className="p-muted" role="status">Getting your accounts…</p>}
      {accounts && (
        <div className="pk">
          <SharedAccountsForm accounts={accounts} busy={busy} error={error} saveLabel="Continue"
                              onSave={onDone} onNone={() => onDone([])} />
        </div>
      )}
      {failed && (
        <div className="p-actions">
          <button type="button" className="p-btn primary" onClick={() => onDone([])}>Skip for now</button>
        </div>
      )}
    </>,
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
