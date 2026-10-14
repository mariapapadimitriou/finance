import { useCallback, useEffect, useState } from 'react';
import {
  deleteAccountNow, deletePasskeyOptions, exportUrl, getDeleteOptions, getExportSummary,
  sendDeleteCode, startOver, syncPlaid,
} from '../api.js';
import { Alert, DetailPanel, PButton } from '../pearl/kit.jsx';
import { BEFORE_YOU_GO, Rows } from '../pearl/privacy.jsx';
import { CodeInput, Heading, Lockup } from '../pearl/ui.jsx';
import { getPasskey, passkeysSupported } from '../pearl/webauthn.js';
import { Field } from './GoalsParts.jsx';
import { PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Your data (THL-116): D-01 Your data, D-02 the download ready,
 * D-03 Before you go, D-04 Confirm it's you, and D-05 Your account is
 * deleted (drawn by App, since she is signed out by then).
 *
 * The download is one .zip — accounts.csv, transactions.csv and
 * settings.json — built on the server from her ledger alone
 * (finance/data_export.py). It's ready in a moment, so the design's emailed
 * link "if you leave this page" isn't needed and isn't drawn.
 *
 * Deleting disconnects her banks at Plaid, removes her ledger, her sign-in
 * and her consent history, and signs her out everywhere, all straight away
 * (finance/account_deletion.py). Only the host's backups take up to 30 days,
 * so the copy says that rather than the design's "within 30 days" for
 * everything. Nothing is deleted until a passkey, an email code or, for an
 * account from before Pearl, the password confirms it's her.
 *
 * Start over (2026-10-14) clears her transactions and her organizing — every
 * answer about a transaction, her rules, income and bills, budgets — and
 * downloads the history again from the banks, which stay connected. Goals,
 * treasure chests and what she set on each account stay. Typing "start over"
 * confirms it (finance/store.py Store.start_over).
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'Your data' }];

// Privacy and consent's "Withdraw" opens straight on Before you go.
let startAt = null;
export function openDataAt(view) { startAt = view; }

const plural = (n, one) => `${n.toLocaleString('en-CA')} ${n === 1 ? one : `${one}s`}`;

/** "84 KB", "1.2 MB". Never "0 KB". */
export function sizeWords(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return null;
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function readyWords(summary) {
  const what = [plural(summary.accounts ?? 0, 'account'),
                plural(summary.transactions ?? 0, 'transaction')].join(' and ');
  return `Your download is ready: ${what}.`;
}

// What Start over does, in her words.
export const START_OVER_ROWS = [
  { title: 'Cleared', sub: 'Every transaction, and everything you sorted: categories, splits, notes, left-out transactions and Needs a look answers.' },
  { title: 'Cleared', sub: 'Your rules, your income and bills setup, and your budgets.' },
  { title: 'Downloaded again', sub: 'Your banks stay connected, and Pearl brings your full history back, ready to sort from scratch.' },
  { title: 'Kept', sub: 'Your goals and treasure chests, with the money you’ve added to them, and your account nicknames and joint shares.' },
  { title: 'Good to know', sub: 'A charge a chest paid for counts in its month again, unless its category belongs to the chest.' },
];

export const START_OVER_WORDS = 'start over';
/** Whether what she typed confirms it, however it's spaced or capitalised. */
export function startOverReady(typed) {
  return String(typed || '').trim().toLowerCase().split(/\s+/).join(' ') === START_OVER_WORDS;
}

/** D-01, and D-02 once `summary` is in. */
export function DataPage({ summary, preparing = false, error = null, onTab, onPrepare, onDelete,
                           onStartOver }) {
  const size = summary && sizeWords(summary.bytes);
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={TRAIL} title="Your data" onTab={onTab}>
        {!summary && <p className="pf-intro">It’s yours. Take a copy any time, or close your account.</p>}
      </PageHead>
      {summary ? (
        <section className="pf-section pv-wide" aria-label="Download a copy">
          <Alert tone="positive">{readyWords(summary)}</Alert>
          <div className="pf-stack">
            <a className="pk-btn primary" href={exportUrl()} download="pearl-data.zip">
              {size ? `Download .zip (${size})` : 'Download .zip'}
            </a>
          </div>
        </section>
      ) : (
        <section className="pf-section" aria-labelledby="dt-copy">
          <h2 className="pk-h3" id="dt-copy">Download a copy</h2>
          <p className="pf-foot">
            A spreadsheet of your accounts and every transaction in Pearl, with the categories
            you chose.
          </p>
          {error && <Alert tone="caution">{error}</Alert>}
          <div className="pf-stack">
            <PButton variant="secondary" onClick={onPrepare} disabled={preparing}>
              {preparing ? 'Getting it ready…' : 'Download my data'}
            </PButton>
          </div>
        </section>
      )}
      {onStartOver && (
        <section className="pf-section" aria-labelledby="dt-start-over">
          <h2 className="pk-h3" id="dt-start-over">Start over</h2>
          <p className="pf-foot">
            Clear your transactions and everything you’ve sorted, and download your history again.
          </p>
          <button type="button" className="pf-text-link" onClick={onStartOver}>Start over</button>
        </section>
      )}
      <section className="pf-section" aria-labelledby="dt-delete">
        <h2 className="pk-h3" id="dt-delete">Delete your account</h2>
        <p className="pf-foot">Disconnects your banks and deletes your data straight away.</p>
        <button type="button" className="pf-text-link" onClick={onDelete}>Delete my account</button>
      </section>
    </div>
  );
}

/** D-03 Before you go. */
export function BeforeYouGo({ onTab, onBack, onDownload, onContinue }) {
  const trail = [{ label: 'Profile', to: 'profile' }, { label: 'Your data', onClick: onBack },
                 { label: 'Delete account' }];
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={trail} title="Before you go" onTab={onTab}>
        <p className="pf-intro">Here’s exactly what happens if you delete your account.</p>
      </PageHead>
      <div className="pv-wide pf-section">
        <Rows rows={BEFORE_YOU_GO} label="What happens" />
        <Alert tone="info" action="Download" onAction={onDownload}>
          Want a copy first? Download your data before you go.
        </Alert>
      </div>
      <div className="pf-actions">
        <PButton onClick={onContinue}>Continue</PButton>
        <PButton variant="secondary" onClick={onBack}>Keep my account</PButton>
      </div>
    </div>
  );
}

/** Before starting over: what goes, what stays, and a copy first. */
export function BeforeYouStart({ onTab, onBack, onDownload, onContinue }) {
  const trail = [{ label: 'Profile', to: 'profile' }, { label: 'Your data', onClick: onBack },
                 { label: 'Start over' }];
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={trail} title="Start over" onTab={onTab}>
        <p className="pf-intro">Here’s exactly what happens if you start over.</p>
      </PageHead>
      <div className="pv-wide pf-section">
        <Rows rows={START_OVER_ROWS} label="What happens" />
        <Alert tone="info" action="Download" onAction={onDownload}>
          Want a copy first? Download your data before you start over.
        </Alert>
      </div>
      <div className="pf-actions">
        <PButton onClick={onContinue}>Continue</PButton>
        <PButton variant="secondary" onClick={onBack}>Keep everything</PButton>
      </div>
    </div>
  );
}

/** Typing "start over" confirms it. */
export function ConfirmStartOver({ typed = '', onTyped, busy = false, error = null, onConfirm,
                                   onClose }) {
  const ready = startOverReady(typed);
  const submit = (e) => { e.preventDefault(); if (ready) onConfirm(); };
  return (
    <DetailPanel label="Start over" overline="" onClose={onClose} className="pf-dialog" sheet>
      <form className="pf-form" onSubmit={submit}>
        <h1 className="pk-h2">Start over?</h1>
        <p className="pk-muted">
          Your transactions and everything you’ve sorted are cleared, and your history downloads
          again. This can’t be undone.
        </p>
        <Field label={`Type “${START_OVER_WORDS}” to confirm`} id="dt-start-over-words">
          <input id="dt-start-over-words" value={typed} autoComplete="off"
                 onChange={(e) => onTyped(e.target.value)} />
        </Field>
        {error && <Alert tone="caution">{error}</Alert>}
        <PButton type="submit" disabled={busy || !ready}>{busy ? 'Starting over…' : 'Start over'}</PButton>
        <PButton variant="text" onClick={onClose}>Cancel</PButton>
      </form>
    </DetailPanel>
  );
}

/** After: downloading, then what came back. */
export function StartedOver({ syncing = false, imported = null, onHome }) {
  let words = 'Pearl will download your history the next time it checks your banks.';
  if (syncing) words = 'Downloading your history from your banks. It can take a minute.';
  else if (imported > 0) {
    words = `${plural(imported, 'transaction')} ${imported === 1 ? 'is' : 'are'} back, ready to sort.`;
  }
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={TRAIL} title={syncing ? 'Starting fresh…' : 'You’re starting fresh'} />
      <div className="pf-section">
        <Alert tone={syncing ? 'info' : 'positive'}>{words}</Alert>
      </div>
      <div className="pf-actions">
        <PButton disabled={syncing} onClick={onHome}>Go to Home</PButton>
      </div>
    </div>
  );
}

/** Which way she confirms first: her passkey, else a code, else her password. */
export function firstMethod(options, canPasskey = passkeysSupported()) {
  const methods = options?.methods ?? [];
  if (canPasskey && methods.includes('passkey')) return 'passkey';
  if (methods.includes('code')) return 'code';
  if (methods.includes('password')) return 'password';
  return null;
}

/** D-04 Confirm it's you. */
export function ConfirmDelete({ options, method, onMethod, code = '', onCode, password = '',
                                onPassword, sentTo = '', busy = false, error = null,
                                onDelete, onResend, onClose, canPasskey = true }) {
  const methods = options?.methods ?? [];
  const other = (m) => m !== method && methods.includes(m) && (m !== 'passkey' || canPasskey);
  const submit = (e) => { e.preventDefault(); onDelete(); };
  return (
    <DetailPanel label="Confirm it’s you" overline="" onClose={onClose} className="pf-dialog" sheet>
      <form className="pf-form" onSubmit={submit}>
        <h1 className="pk-h2">Confirm it’s you</h1>
        {method === 'passkey' && (
          <p className="pk-muted">Use your passkey to delete your account. This can’t be undone.</p>
        )}
        {method === 'code' && (
          <>
            <p className="pk-muted">
              {sentTo ? `We sent a 6-digit code to ${sentTo}. Enter it to delete your account. This can’t be undone.`
                : 'We’re sending a 6-digit code to your email.'}
            </p>
            <CodeInput value={code} onChange={onCode} error={!!error} />
          </>
        )}
        {method === 'password' && (
          <>
            <p className="pk-muted">Enter your password to delete your account. This can’t be undone.</p>
            <Field label="Password" id="dt-password">
              <input id="dt-password" type="password" autoComplete="current-password"
                     value={password} onChange={(e) => onPassword(e.target.value)} />
            </Field>
          </>
        )}
        {error && <Alert tone="caution">{error}</Alert>}
        <PButton type="submit" disabled={busy}>{busy ? 'Deleting…' : 'Delete my account'}</PButton>
        {method === 'code' && sentTo && (
          <PButton variant="text" disabled={busy} onClick={onResend}>Send a new code</PButton>
        )}
        {other('code') && (
          <PButton variant="text" onClick={() => onMethod('code')}>Use an email code instead</PButton>
        )}
        {other('passkey') && (
          <PButton variant="text" onClick={() => onMethod('passkey')}>Use your passkey instead</PButton>
        )}
        {other('password') && method !== 'passkey' && (
          <PButton variant="text" onClick={() => onMethod('password')}>Use your password instead</PButton>
        )}
        <PButton variant="text" onClick={onClose}>Cancel</PButton>
      </form>
    </DetailPanel>
  );
}

/** D-05, full screen: she is signed out by the time it shows. */
export function AccountDeleted({ sentTo, onClose }) {
  return (
    <div className="pearl pv-gone">
      <main className="p-body">
        <div className="p-form">
          <Lockup />
          <Heading title="Your account is deleted"
                   sub="We’ve disconnected your banks, signed you out and deleted your data. Anything left in our host’s backups is gone within 30 days." />
          {sentTo && <p className="p-small">{`We’ve sent a confirmation to ${sentTo}.`}</p>}
          <div className="p-actions">
            <button type="button" className="p-btn secondary" onClick={onClose}>Close</button>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function DataPanel({ onTab, onDeleted, onChanged }) {
  const [view, setView] = useState(() => { const v = startAt; startAt = null; return v ?? 'page'; });
  const [summary, setSummary] = useState(null);
  const [preparing, setPreparing] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [options, setOptions] = useState(null);
  const [method, setMethod] = useState(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [sentTo, setSentTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [typed, setTyped] = useState('');
  const [fresh, setFresh] = useState(null);
  useEffect(() => { window.scrollTo?.(0, 0); }, [view]);

  async function beginAgain() {
    setBusy(true);
    setError(null);
    try {
      await startOver();
      setFresh({ syncing: true, imported: null });
      setView('fresh');
      let imported = null;
      try { imported = (await syncPlaid(true))?.imported ?? null; } catch { /* next sync */ }
      setFresh({ syncing: false, imported });
      await onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const prepare = useCallback(async () => {
    setPreparing(true);
    setExportError(null);
    try {
      setSummary(await getExportSummary());
    } catch (e) {
      setExportError(e.message);
    } finally {
      setPreparing(false);
    }
  }, []);

  const sendCode = useCallback(async () => {
    setError(null);
    const r = await sendDeleteCode().catch((e) => ({ ok: false, error: e.message }));
    if (!r.ok) { setError(r.error || 'The code didn’t send. Try again in a minute.'); return; }
    setSentTo(r.sent_to || '');
    setCode('');
  }, []);

  const choose = useCallback((m) => {
    setMethod(m);
    setError(null);
    if (m === 'code') sendCode();
  }, [sendCode]);

  async function openConfirm() {
    setError(null);
    try {
      const o = await getDeleteOptions();
      setOptions(o);
      const first = firstMethod(o);
      if (!first) { setError('There’s no way to confirm it’s you on this account.'); return; }
      choose(first);
      setView('confirm');
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      let proof;
      if (method === 'passkey') {
        proof = { method, credential: await getPasskey(await deletePasskeyOptions()) };
      } else if (method === 'code') {
        if (code.length < 6) { setError('Enter all six digits.'); return; }
        proof = { method, code };
      } else {
        proof = { method, password };
      }
      const r = await deleteAccountNow(proof);
      if (!r.ok) { setError(r.error || 'That didn’t work. Try again.'); return; }
      onDeleted?.({ sentTo: r.confirmation_sent_to || null });
    } catch (e) {
      setError(e.name === 'NotAllowedError'
        ? 'The passkey prompt was closed. Try again, or use an email code instead.' : e.message);
    } finally {
      setBusy(false);
    }
  }

  if (view === 'fresh') {
    return <StartedOver syncing={fresh?.syncing} imported={fresh?.imported}
                        onHome={() => onTab?.('home')} />;
  }
  if (view === 'start' || view === 'start-confirm') {
    return (
      <>
        <BeforeYouStart onTab={onTab} onBack={() => setView('page')}
                        onContinue={() => { setTyped(''); setError(null); setView('start-confirm'); }}
                        onDownload={() => { setView('page'); prepare(); }} />
        {view === 'start-confirm' && (
          <div className="pk">
            <ConfirmStartOver typed={typed} onTyped={(v) => { setTyped(v); setError(null); }}
                              busy={busy} error={error} onConfirm={beginAgain}
                              onClose={() => { setView('start'); setError(null); }} />
          </div>
        )}
      </>
    );
  }
  if (view === 'delete' || view === 'confirm') {
    return (
      <>
        <BeforeYouGo onTab={onTab} onBack={() => setView('page')} onContinue={openConfirm}
                     onDownload={() => { setView('page'); prepare(); }} />
        {view === 'delete' && error && <div className="pk pv-page"><Alert tone="caution">{error}</Alert></div>}
        {view === 'confirm' && (
          <div className="pk">
            <ConfirmDelete options={options} method={method} onMethod={choose} code={code}
                           onCode={(v) => { setCode(v); setError(null); }}
                           password={password} onPassword={setPassword} sentTo={sentTo}
                           busy={busy} error={error} onDelete={remove} onResend={sendCode}
                           canPasskey={passkeysSupported()}
                           onClose={() => { setView('delete'); setError(null); }} />
          </div>
        )}
      </>
    );
  }
  return (
    <DataPage summary={summary} preparing={preparing} error={exportError} onTab={onTab}
              onPrepare={prepare} onDelete={() => setView('delete')}
              onStartOver={() => setView('start')} />
  );
}
