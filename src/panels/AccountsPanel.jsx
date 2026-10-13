import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  addManualAccount, createLinkToken, exchangePublicToken, getAccountsOverview, keepAsManual,
  removeAccount, saveAccountSettings, syncPlaid, updateManualBalance,
} from '../api.js';
import { loadPlaidScript } from '../plaid.js';
import {
  ActionToast, Alert, Choice, DetailPanel, PButton, StatTile, StatusPill, Toast,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Field, parseAmount } from './GoalsParts.jsx';
import { MONTH_NAMES, ReconnectPanel, shown } from './HomePanel.jsx';
import { ListRow, PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Accounts (THL-120; Pearl "Accounts & settings" AM-01 to AM-07,
 * C-01 and C-06).
 *
 *   AM-01 / C-01  every account, Linked and Added by you, with its state
 *   AM-02 / AM-03 one account: how it counts (Count in my budget, joint),
 *                 a nickname, and Remove; leaving it out says what safe to
 *                 spend is now, with Undo
 *   AM-04         her share of a joint account
 *   AM-05 / AM-06 a balance added by hand, and its page
 *   AM-07         remove an account, keeping or deleting its transactions
 *   C-06          a disconnected account: Reconnect, keep it as a manual
 *                 account, or remove it
 *
 * Linking a bank (Plaid Link), signing in to one again (update mode,
 * `createLinkToken(itemId)`, C-04) and syncing afterwards live here since
 * Connections went (C1). Calm copy: states in words and an icon, never
 * colour alone; no red; amounts without a sign; one primary action a screen.
 */

const plural = (n, one, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** "October 1" from "2026-10-01" (or an ISO timestamp). */
export const monthDay = (iso) => `${MONTH_NAMES[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;
/** "March 2026". */
export const monthYear = (iso) => `${MONTH_NAMES[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;

/** "5 minutes ago", "6 hours ago", "Tuesday, October 6" — when it last updated. */
export function updatedWords(iso, now = Date.now(), short = false) {
  if (!iso) return null;
  const at = Date.parse(iso.length <= 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(at)) return null;
  const mins = Math.max(0, Math.round((now - at) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return short ? `${mins} min ago` : `${plural(mins, 'minute')} ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return short ? `${hours} hr ago` : `${plural(hours, 'hour')} ago`;
  const d = new Date(at);
  const day = `${MONTH_NAMES[d.getMonth()]} ${d.getDate()}`;
  return short ? day : `${DAYS[d.getDay()]}, ${day}`;
}

/** The account's balance as a phrase: "$412.55 owing", "$2,340.18". */
export function balanceWords(a) {
  if (a.balance === null || a.balance === undefined || Number.isNaN(Number(a.balance))) return null;
  const n = Math.abs(Number(a.balance));
  if (n < 0.005) return a.owing ? 'Nothing owing' : 'Nothing in it';
  return a.owing ? `${shown(n, true)} owing` : shown(n, true);
}

/** A tile's figure: the amount alone, the tile's label says "owing". */
export function tileAmount(a) {
  if (a.balance === null || a.balance === undefined || Number.isNaN(Number(a.balance))) return null;
  const n = Math.abs(Number(a.balance));
  if (n < 0.005) return a.owing ? 'Nothing owing' : 'Nothing in it';
  return shown(n, true);
}

/** "TD Visa ••1203". */
export const titleOf = (a) => (a.mask ? `${a.name} ••${a.mask}` : a.name);

/** What the row under the name says (AM-01, C-01). */
export function accountMeta(a, now = Date.now()) {
  const bal = balanceWords(a);
  const updated = updatedWords(a.updated_at, now);
  let rest;
  if (a.source === 'statement') {
    return `${plural(a.transactions, 'transaction')} from a statement`;
  }
  if (a.source === 'hand') rest = a.updated_at ? `you updated it ${monthDay(a.updated_at)}` : null;
  else if (a.status === 'disconnected') {
    rest = a.disconnected_on ? `disconnected on ${monthDay(a.disconnected_on)}` : 'disconnected';
  } else if (a.status === 'sign_in' || a.status === 'retrying') {
    rest = updated ? `last updated ${updated}` : null;
  } else if (a.status === 'not_counted') rest = 'not in your budget';
  else if (a.joint) rest = a.joint_share ? `joint, your share is ${Math.round(a.joint_share)}%` : 'joint';
  else if (a.anchor) rest = 'counts toward your Anchor';
  else rest = updated ? `updated ${updated}` : 'waiting for its first update';
  const out = [bal, rest].filter(Boolean).join(' · ');
  return out.charAt(0).toUpperCase() + out.slice(1);
}

/** The status pill (C-01): the state in a word, with an icon. */
export function pillFor(a) {
  switch (a.status) {
    case 'up_to_date': return { label: 'Up to date', tone: 'positive', icon: 'check' };
    case 'joint': return { label: 'Joint', tone: 'info', icon: 'info' };
    case 'not_counted': return { label: 'Not counted', tone: 'neutral', icon: null };
    case 'manual': return { label: 'Manual', tone: 'neutral', icon: null };
    case 'sign_in': return { label: 'Sign in again', tone: 'caution', icon: 'alert' };
    case 'retrying': return { label: 'We’re retrying', tone: 'info', icon: 'info' };
    case 'disconnected': return { label: 'Disconnected', tone: 'neutral', icon: null };
    default: return null;
  }
}

const needsReconnect = (a) => a.status === 'sign_in' || a.status === 'disconnected';

/** Two to three letters for the avatar, from the bank: "TD", "T", "AB". */
export function bankInitials(a) {
  const words = String(a.institution || a.bank_name || a.name || '')
    .replace(/[^A-Za-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean);
  if (!words.length) return '•';
  const first = words[0];
  if (first.length <= 3 && first === first.toUpperCase()) return first;
  if (words.length === 1) return first[0].toUpperCase();
  return (first[0] + words[1][0]).toUpperCase();
}

function AccountRow({ a, onOpen, onReconnect, now }) {
  const pill = pillFor(a);
  const reconnect = needsReconnect(a);
  return (
    <li className="pf-row">
      <button type="button" className="pf-row-main" onClick={() => onOpen(a)}>
        <span className="pk-avatar" aria-hidden="true">{bankInitials(a)}</span>
        <span className="pf-row-text">
          <span className="pf-row-name">{titleOf(a)}</span>
          <span className="pf-row-sub">{accountMeta(a, now)}</span>
        </span>
        <span className="pf-row-end">
          {pill && <StatusPill icon={pill.icon} tone={pill.tone}>{pill.label}</StatusPill>}
          {!reconnect && <PIcon name="chevronRight" size={18} />}
        </span>
      </button>
      {reconnect && (
        <button type="button" className="pf-row-link" onClick={() => onReconnect(a)}>
          Reconnect <PIcon name="chevronRight" size={14} />
        </button>
      )}
    </li>
  );
}

/** AM-01 / C-01: every account, and the two ways to add one. */
export function AccountsList({ data, onTab, onOpen, onReconnect, onLink, onAdd, linking = false,
                               now = Date.now() }) {
  const { linked = [], added = [], plaid = {} } = data;
  const canLink = plaid.configured && plaid.encryption_ready;
  const mixed = (data.currency_mix ?? []).length > 1;
  const none = linked.length === 0 && added.length === 0;
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={[{ label: 'Profile', to: 'profile' }, { label: 'Accounts' }]}
                title="Accounts" onTab={onTab} />
      <p className="pf-intro">
        {none ? 'Link your bank and Pearl does the rest. Or add a balance by hand for a bank Pearl can’t link yet.'
          : 'Pearl checks your banks a few times a day. Every balance shows when it was last updated.'}
      </p>
      {mixed && (
        <Alert tone="info">
          {`Your accounts hold ${data.currency_mix.length} currencies, so totals that mix them are approximate.`}
        </Alert>
      )}
      {linked.length > 0 && (
        <section className="pf-section" aria-labelledby="ac-linked">
          <h2 className="pk-h3" id="ac-linked">Linked</h2>
          <ul className="pf-list">
            {linked.map((a) => <AccountRow key={a.id} a={a} onOpen={onOpen} onReconnect={onReconnect} now={now} />)}
          </ul>
        </section>
      )}
      {added.length > 0 && (
        <section className="pf-section" aria-labelledby="ac-added">
          <h2 className="pk-h3" id="ac-added">Added by you</h2>
          <ul className="pf-list">
            {added.map((a) => <AccountRow key={a.id} a={a} onOpen={onOpen} onReconnect={onReconnect} now={now} />)}
          </ul>
        </section>
      )}
      <div className="pf-actions">
        <PButton onClick={onLink} disabled={!canLink || linking}>
          {linking ? 'Opening…' : linked.length ? 'Link another bank' : 'Link your bank'}
        </PButton>
        <PButton variant="secondary" onClick={onAdd}>Add a balance by hand</PButton>
      </div>
      {!plaid.configured && (
        <p className="pf-foot">Linking a bank isn’t set up on this copy of Pearl yet.</p>
      )}
      {plaid.configured && !plaid.encryption_ready && (
        <p className="pf-foot">Linking a bank needs an encryption key on this copy of Pearl first.</p>
      )}
      {plaid.configured && plaid.environment === 'sandbox' && (
        <p className="pf-foot">Plaid sandbox: test banks only.</p>
      )}
    </div>
  );
}

const trailFor = (a, onBack) => [
  { label: 'Profile', to: 'profile' },
  { label: 'Accounts', onClick: onBack },
  { label: a.name },
];

/** AM-02, AM-03, AM-06 and C-06: one account. */
export function AccountDetail({ a, onTab, onBack, onSave, onShare, onRemove, onReconnect,
                                onKeepManual, onUpdateBalance, now = Date.now(), busy = false }) {
  const [nickname, setNickname] = useState(a.nickname || a.bank_name || '');
  useEffect(() => { setNickname(a.nickname || a.bank_name || ''); }, [a.id, a.nickname, a.bank_name]);
  const trail = trailFor(a, onBack);
  const head = <PageHead trail={trail} title={titleOf(a)} onTab={onTab} />;
  const history = a.history_from ? monthYear(a.history_from) : null;
  const saveNickname = () => {
    let next = nickname.trim();
    if (next === a.bank_name) next = '';
    if (next !== (a.nickname || '')) onSave({ nickname: next });
  };

  if (a.source === 'hand') {
    return (
      <div className="pk hm-page pf-page">
        {head}
        <div className="pf-tiles">
          <StatTile label={a.owing ? 'Balance owing' : 'Balance'} value={tileAmount(a) ?? 'Not added'} />
          {a.updated_at && <StatTile label="You updated it" value={monthDay(a.updated_at)} />}
        </div>
        <p className="pk-label pk-muted">
          Added by you. Pearl can’t see its transactions, so it only counts in your snapshot.
        </p>
        <div className="pf-stack">
          <PButton variant="secondary" onClick={onUpdateBalance}>Update balance</PButton>
        </div>
        <div className="pk-choices">
          <Choice type="checkbox" checked={a.counted} disabled={busy}
                  onChange={(on) => onSave({ counted: on })} label="Count in my snapshot" />
          <Choice type="checkbox" checked={a.anchor} disabled={busy || !a.can_anchor}
                  onChange={(on) => onSave({ anchor: on })} label="Counts toward my Anchor"
                  description="Savings accounts only" />
        </div>
        <button type="button" className="pf-text-link" onClick={() => onRemove()}>
          Remove this account
        </button>
      </div>
    );
  }

  if (a.status === 'disconnected') {
    const on = a.disconnected_on ? monthDay(a.disconnected_on) : null;
    return (
      <div className="pk hm-page pf-page">
        {head}
        <Alert tone="info">
          {`${on ? `Disconnected on ${on}.` : 'Disconnected.'} Your past transactions stay in Pearl, but new ones won’t come in.`}
        </Alert>
        <div className="pf-tiles">
          {tileAmount(a) && (
            <StatTile label={on ? `Balance on ${on}` : 'Last balance'} value={tileAmount(a)} />
          )}
          <StatTile label="Transactions in Pearl" value={a.transactions.toLocaleString()} />
          {history && <StatTile label="History from" value={history} />}
        </div>
        <div className="pf-stack">
          <PButton onClick={() => onReconnect(a)}>Reconnect</PButton>
          <PButton variant="secondary" disabled={busy} onClick={onKeepManual}>
            Keep it as a manual account
          </PButton>
          <button type="button" className="pf-text-link" onClick={() => onRemove('delete')}>
            Or remove this account and its history from Pearl.
          </button>
        </div>
      </div>
    );
  }

  const linked = a.source === 'plaid';
  const updated = updatedWords(a.updated_at, now, true);
  return (
    <div className="pk hm-page pf-page">
      {head}
      {a.status === 'sign_in' && (
        <Alert tone="caution" action="Reconnect" onAction={() => onReconnect(a)}>
          {`${a.institution || 'Your bank'} needs you to sign in again. Transactions since ${updatedWords(a.updated_at, now) ?? 'then'} aren’t counted yet.`}
        </Alert>
      )}
      {a.status === 'retrying' && (
        <Alert tone="info">
          {`${a.institution || 'Your bank'} isn’t responding right now. We’ll keep trying; there’s nothing you need to do.`}
        </Alert>
      )}
      {!a.counted && (
        <Alert tone="info">
          This account isn’t in your budget. Its transactions stay here, but they don’t count toward
          safe to spend, spending or your snapshot.
        </Alert>
      )}
      <div className="pf-tiles">
        {tileAmount(a) && <StatTile label={a.owing ? 'Balance owing' : 'Balance'} value={tileAmount(a)} />}
        {linked && updated && <StatTile label="Updated" value={updated} />}
        {!linked && <StatTile label="Transactions" value={a.transactions.toLocaleString()} />}
        {history && <StatTile label="History from" value={history} />}
      </div>
      <section className="pf-section" aria-labelledby="ac-counts">
        <h2 className="pk-h3" id="ac-counts">How it counts</h2>
        <div className="pk-choices">
          <Choice type="checkbox" checked={a.counted} disabled={busy}
                  onChange={(on) => onSave({ counted: on })} label="Count in my budget"
                  description="Its spending, bills and balance count toward safe to spend and your snapshot." />
          {linked && (
            <Choice type="checkbox" checked={a.joint} disabled={busy}
                    onChange={(on) => (on ? onShare() : onSave({ joint_share: null }))}
                    label="This is a joint account"
                    description={a.joint && a.joint_share
                      ? `Only your share counts. Your share is ${Math.round(a.joint_share)}%.`
                      : 'Only your share counts. You choose the share.'} />
          )}
          {a.can_anchor && (
            <Choice type="checkbox" checked={a.anchor} disabled={busy}
                    onChange={(on) => onSave({ anchor: on })} label="Counts toward my Anchor"
                    description="Savings accounts only" />
          )}
        </div>
        {a.joint && (
          <button type="button" className="pf-text-link" onClick={onShare}>Change your share</button>
        )}
      </section>
      <form className="pf-form" onSubmit={(e) => { e.preventDefault(); saveNickname(); }}>
        <Field label="Nickname" id="ac-nickname">
          <input id="ac-nickname" autoComplete="off" maxLength={40} value={nickname}
                 placeholder={a.bank_name} onChange={(e) => setNickname(e.target.value)}
                 onBlur={saveNickname} />
        </Field>
      </form>
      <button type="button" className="pf-text-link" onClick={() => onRemove()}>
        Remove this account
      </button>
    </div>
  );
}

/** AM-07: remove an account, keeping or deleting its transactions. */
export function RemoveDialog({ a, start = 'keep', onClose, onRemove }) {
  const [what, setWhat] = useState(start);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const hand = a.source === 'hand';
  const go = () => {
    setBusy(true);
    setError(null);
    onRemove(hand ? 'keep' : what).catch((e) => { setError(e.message); setBusy(false); });
  };
  return (
    <DetailPanel label={`Remove ${a.name}?`} overline="" onClose={onClose} className="pf-dialog" sheet>
      <h1 className="pk-h2">{`Remove ${a.name}?`}</h1>
      <p className="pk-muted">
        {hand ? 'It comes out of your snapshot straight away.'
          : a.source === 'plaid'
            ? 'Pearl stops syncing it and disconnects it from your bank straight away.'
            : 'It comes off your accounts straight away.'}
      </p>
      {!hand && a.transactions > 0 && (
        <>
          <h2 className="pk-h3">{`Its ${plural(a.transactions, 'transaction')}`}</h2>
          <div className="pk-choices" role="radiogroup" aria-label="Its transactions">
            <Choice name="ac-keep" checked={what === 'keep'} onChange={() => setWhat('keep')}
                    label="Keep them" description="Past months stay accurate. Nothing new comes in." />
            <Choice name="ac-keep" checked={what === 'delete'} onChange={() => setWhat('delete')}
                    label="Delete them too" description="Your averages will change. This can’t be undone." />
          </div>
        </>
      )}
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton onClick={go} disabled={busy}>{busy ? 'Removing…' : 'Remove account'}</PButton>
      <PButton variant="text" onClick={onClose}>Keep it</PButton>
    </DetailPanel>
  );
}

/** "50", "50%", " 33.5 % " → 50, 50, 33.5; anything else → NaN. */
export function parseShare(text) {
  const clean = String(text ?? '').replace(/[%\s]/g, '');
  return /^\d+(\.\d{1,2})?$/.test(clean) ? Number(clean) : NaN;
}

/** AM-04: her share of a joint account. */
export function ShareDialog({ a, onClose, onSave }) {
  const initial = a.joint_share ?? 50;
  const [half, setHalf] = useState(initial === 50);
  const [text, setText] = useState(`${initial}%`);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const share = half ? 50 : parseShare(text);
    if (Number.isNaN(share) || share < 1 || share > 99) {
      setError('Enter a share between 1% and 99%.');
      return;
    }
    setBusy(true);
    setError(null);
    onSave(share).catch((err) => { setError(err.message); setBusy(false); });
  };
  return (
    <DetailPanel label={`Your share of ${a.name}`} overline="" onClose={onClose} className="pf-dialog" sheet>
      <form className="pf-form" onSubmit={submit}>
        <h1 className="pk-h2">{`Your share of ${a.name}`}</h1>
        <p className="pk-muted">
          Only your share of its spending, income and balance will count. Change it any time.
        </p>
        <div className="pk-choices" role="radiogroup" aria-label="Your share">
          <Choice name="ac-share" checked={half} label="Half (50%)"
                  onChange={() => { setHalf(true); setText('50%'); setError(null); }} />
          <Choice name="ac-share" checked={!half} label="A different share"
                  onChange={() => { setHalf(false); setError(null); }} />
        </div>
        <Field label="Your share" id="ac-share-pc" error={error}>
          <input id="ac-share-pc" inputMode="decimal" autoComplete="off" value={text}
                 onChange={(e) => { setText(e.target.value); setHalf(false); setError(null); }} />
          {!error && <p className="gl-hint">Between 1% and 99%</p>}
        </Field>
        <PButton type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</PButton>
        <PButton variant="text" onClick={onClose}>Cancel</PButton>
      </form>
    </DetailPanel>
  );
}

/** AM-06 "Update balance": what a hand-added account holds today. */
export function BalanceDialog({ a, onClose, onSave }) {
  const [text, setText] = useState(a.balance ? String(a.balance) : '');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const n = parseAmount(text);
    if (!text.trim() || Number.isNaN(n)) { setError('Enter the balance today, like 3,000.'); return; }
    setBusy(true);
    onSave(n).catch((err) => { setError(err.message); setBusy(false); });
  };
  return (
    <DetailPanel label={`Update ${a.name}`} overline="" onClose={onClose} className="pf-dialog" sheet>
      <form className="pf-form" onSubmit={submit}>
        <h1 className="pk-h2">{`Update ${a.name}`}</h1>
        <p className="pk-muted">What it holds today, from your bank’s app or statement.</p>
        <Field label={a.owing ? 'Balance owing today' : 'Balance today'} id="ac-balance-new" error={error}>
          <input id="ac-balance-new" inputMode="decimal" autoComplete="off" placeholder="$3,000.00"
                 value={text} onChange={(e) => { setText(e.target.value); setError(null); }} />
        </Field>
        <PButton type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</PButton>
        <PButton variant="text" onClick={onClose}>Cancel</PButton>
      </form>
    </DetailPanel>
  );
}

const KINDS = [
  { value: 'chequing', label: 'Chequing' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit', label: 'Credit card', description: 'Counts as money you owe' },
];

/** AM-05: add a balance by hand. */
export function AddByHand({ onTab, onBack, onAdd }) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState('savings');
  const [balance, setBalance] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    if (!name.trim()) { setError({ field: 'name', text: 'Give it a name, like the bank and account.' }); return; }
    const n = parseAmount(balance);
    if (!balance.trim() || Number.isNaN(n)) {
      setError({ field: 'balance', text: 'Enter the balance today, like 3,000.' });
      return;
    }
    setBusy(true);
    setError(null);
    onAdd(name.trim(), kind, n).catch((err) => {
      setError({ field: 'balance', text: err.message });
      setBusy(false);
    });
  };
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={[{ label: 'Profile', to: 'profile' }, { label: 'Accounts', onClick: onBack },
                        { label: 'Add a balance' }]}
                title="Add a balance by hand" onTab={onTab} />
      <p className="pf-intro">
        For a bank Pearl can’t link yet. The balance shows in your snapshot. Transactions won’t
        come in, so it won’t change your spending.
      </p>
      <form className="pf-form" onSubmit={submit} noValidate>
        <Field label="Name" id="ac-name" error={error?.field === 'name' ? error.text : null}>
          <input id="ac-name" autoComplete="off" maxLength={40} placeholder="Meridian Savings"
                 value={name} onChange={(e) => { setName(e.target.value); setError(null); }} />
        </Field>
        <h2 className="pk-h3">Type</h2>
        <div className="pk-choices" role="radiogroup" aria-label="Type">
          {KINDS.map((k) => (
            <Choice key={k.value} name="ac-kind" checked={kind === k.value}
                    onChange={() => setKind(k.value)} label={k.label} description={k.description} />
          ))}
        </div>
        <Field label={kind === 'credit' ? 'Balance owing today' : 'Balance today'} id="ac-balance"
               error={error?.field === 'balance' ? error.text : null}>
          <input id="ac-balance" inputMode="decimal" autoComplete="off" placeholder="$3,000.00"
                 value={balance} onChange={(e) => { setBalance(e.target.value); setError(null); }} />
        </Field>
        <PButton type="submit" disabled={busy}>{busy ? 'Adding…' : 'Add account'}</PButton>
        <PButton variant="text" onClick={onBack}>Cancel</PButton>
      </form>
    </div>
  );
}

/** The toast after Count in my budget changes (AM-03). */
export function countedToast(a, counted, safeToSpend) {
  const what = counted ? `${a.name} counts again.` : `${a.name} no longer counts.`;
  const sts = safeToSpend > 0 ? ` Safe to spend is now ${shown(safeToSpend, true)}.` : '';
  return `${what}${sts}`;
}

export default function AccountsPanel({ onChanged, onTab, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState({ name: 'list' });
  const [dialog, setDialog] = useState(null);
  const [toast, setToast] = useState(null);
  const [note, setNote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [linking, setLinking] = useState(false);
  const [reconnect, setReconnect] = useState(null);

  const load = useCallback(() => getAccountsOverview().then(setData).catch(setError), []);
  useEffect(() => { load(); }, [load, version]);
  // A new page within Accounts opens at its top, as a new panel would.
  useEffect(() => { window.scrollTo?.(0, 0); }, [view.name, view.id]);

  const refresh = async () => { await load(); await onChanged?.(); };

  /** Open Plaid Link for a new bank; the public token becomes an item here. */
  async function openLink() {
    setLinking(true);
    setError(null);
    try {
      const [Plaid, { link_token: token }] = await Promise.all([
        loadPlaidScript(), createLinkToken()]);
      Plaid.create({
        token,
        onSuccess: async (publicToken, metadata) => {
          try {
            const r = await exchangePublicToken(publicToken, metadata?.institution?.name || '');
            if (!r.sync) await syncPlaid();
            setNote(`${metadata?.institution?.name || 'Your bank'} is linked.`);
            await refresh();
          } catch (e) {
            setError(e);
          } finally {
            setLinking(false);
          }
        },
        onExit: (err) => {
          setLinking(false);
          if (err) setError(new Error(err.display_message || err.error_message || 'Linking didn’t finish. You can try again.'));
        },
      }).open();
    } catch (e) {
      setError(e);
      setLinking(false);
    }
  }

  // Reconnect (C-04): Link in update mode for a login Pearl still holds; a
  // login that's gone entirely is linked afresh.
  const onReconnect = (a) => {
    if (a.item_id) setReconnect({ item_id: a.item_id, institution: a.institution || a.name });
    else openLink();
  };

  async function save(a, fields) {
    setBusy(true);
    setError(null);
    try {
      const r = await saveAccountSettings(a.id, fields);
      if (r.resync) { try { await syncPlaid(); } catch { /* the next sync catches up */ } }
      if ('counted' in fields && a.source !== 'hand') {
        setToast({ text: countedToast(r.account ?? a, fields.counted, r.safe_to_spend),
                   undo: () => save(a, { counted: !fields.counted }) });
      } else if ('nickname' in fields) {
        setNote('Nickname saved.');
      }
      await refresh();
      return r;
    } catch (e) {
      setError(e);
      throw e;
    } finally {
      setBusy(false);
    }
  }

  if (!data && error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading your accounts…</p></div>;

  const all = [...data.linked, ...data.added];
  const current = view.name === 'detail' ? all.find((a) => a.id === view.id) : null;
  const back = () => { setView({ name: 'list' }); setDialog(null); };

  let page;
  if (view.name === 'add') {
    page = (
      <AddByHand onTab={onTab} onBack={back}
                 onAdd={async (name, kind, balance) => {
                   const r = await addManualAccount(name, kind, balance);
                   setNote(`${r.account?.name ?? name} is added.`);
                   await refresh();
                   setView({ name: 'list' });
                 }} />
    );
  } else if (current) {
    page = (
      <AccountDetail a={current} onTab={onTab} onBack={back} busy={busy}
                     onSave={(fields) => save(current, fields).catch(() => {})}
                     onShare={() => setDialog({ kind: 'share' })}
                     onRemove={(start = 'keep') => setDialog({ kind: 'remove', start })}
                     onReconnect={onReconnect}
                     onUpdateBalance={() => setDialog({ kind: 'balance' })}
                     onKeepManual={async () => {
                       setBusy(true);
                       try {
                         const r = await keepAsManual(current.id);
                         setNote(`${current.name} is now a manual account.`);
                         await refresh();
                         setView(r.account ? { name: 'detail', id: r.account.id } : { name: 'list' });
                       } catch (e) { setError(e); } finally { setBusy(false); }
                     }} />
    );
  } else {
    page = (
      <AccountsList data={data} onTab={onTab} linking={linking}
                    onOpen={(a) => setView({ name: 'detail', id: a.id })}
                    onReconnect={onReconnect} onLink={openLink}
                    onAdd={() => setView({ name: 'add' })} />
    );
  }

  return (
    <>
      {error && <div className="pk"><ErrorNote error={error} /></div>}
      {page}
      <div className="pk">
        {current && dialog?.kind === 'remove' && (
          <RemoveDialog a={current} start={dialog.start} onClose={() => setDialog(null)}
                        onRemove={async (what) => {
                          await removeAccount(current.id, what);
                          setNote(`${current.name} is removed.`);
                          back();
                          await refresh();
                        }} />
        )}
        {current && dialog?.kind === 'share' && (
          <ShareDialog a={current} onClose={() => setDialog(null)}
                       onSave={async (share) => { await save(current, { joint_share: share }); setDialog(null); }} />
        )}
        {current && dialog?.kind === 'balance' && (
          <BalanceDialog a={current} onClose={() => setDialog(null)}
                         onSave={async (n) => {
                           await updateManualBalance(current.id, n);
                           setDialog(null);
                           setNote('Balance updated.');
                           await refresh();
                         }} />
        )}
      </div>
      {reconnect && (
        <div className="pk">
          <ReconnectPanel connection={reconnect} onClose={() => setReconnect(null)}
                          onDone={async () => {
                            setReconnect(null);
                            setNote(`${reconnect.institution} is back up to date.`);
                            await refresh();
                          }} />
        </div>
      )}
      {toast && (
        <div className="pk">
          <ActionToast title={toast.text} onUndo={() => { const u = toast.undo; setToast(null); u(); }}
                       onDone={() => setToast(null)} />
        </div>
      )}
      {note && !toast && <div className="pk"><Toast onDone={() => setNote(null)}>{note}</Toast></div>}
    </>
  );
}
