import { useEffect, useId, useState } from 'react';
import {
  Avatar, CategoryChip, DetailPanel, PButton, StatusPill, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import {
  addTransaction, allocateToBank, confirmTx, excludeTransaction, getBanks, getTx,
  includeTransaction, money, setCategory, setMineAlways, setShare, setTxNote, sortTransfers,
  unallocate,
} from '../api.js';

/**
 * One transaction (Pearl TX-04, THL-122): a 560px panel over the list, the
 * whole page on a phone.
 *
 * A suggested category asks "Is it right?": yes confirms it and closes with
 * "Saved"; once confirmed the question and the button go and only Change
 * category stays. Change category (R-02) and Split this (S-01, THL-124) are
 * not designed yet, so each is a plain step inside the panel until they are.
 */

const NOTE_MAX = 140;
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function longDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return `${WEEKDAYS[date.getDay()]}, ${MONTHS[m - 1]} ${d}`
    + (y !== new Date().getFullYear() ? `, ${y}` : '');
}

/** Why Pearl thinks what it thinks, in a sentence. */
function suggestionReason(tx) {
  if (tx.category === 'Unsorted transfers') {
    return 'This went somewhere Pearl can’t see. Was it saved or spent?';
  }
  if (tx.category_source === 'issuer') return 'Your bank suggested this. Is it right?';
  if (tx.category_source === 'destination') {
    return 'Pearl sorted this the way you sorted earlier transfers to the same place. Is it right?';
  }
  return 'Pearl suggested this from the merchant name. Is it right?';
}

export default function TransactionDetail({ id, initial, categories, onClose, onSaved }) {
  const [tx, setTx] = useState(initial && initial.id === id ? initial : null);
  const [error, setError] = useState(null);
  // main | category | split | note | exclude | bank | whose
  const [step, setStep] = useState('main');
  const [busy, setBusy] = useState(false);
  const [banks, setBanks] = useState([]);

  useEffect(() => {
    let live = true;
    getTx(id).then((r) => { if (live) setTx(r); }).catch((e) => { if (live) setError(e); });
    getBanks().then((d) => { if (live) setBanks(d.banks ?? []); }).catch(() => {});
    return () => { live = false; };
  }, [id]);

  async function save(fn, { close = false } = {}) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onSaved?.({ close });
      if (close) return;
      setTx(await getTx(id));
      setStep('main');
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!tx) {
    return (
      <DetailPanel label="Transaction" overline="Transaction" onClose={onClose}>
        {error ? <p className="pk-muted" role="status">We couldn’t open this transaction.</p>
          : <p className="pk-muted">Loading…</p>}
      </DetailPanel>
    );
  }

  const muted = tx.counts === 'none';
  const left = !!tx.excluded;
  const notYours = tx.chip.label === 'Not yours';
  const canConfirm = tx.suggested && tx.category !== 'Unsorted transfers' && !left;
  const canSplit = tx.counts === 'spending' && !tx.inflow && !left && !tx.joint;
  // A piggy bank can pay for a charge (not money coming in, not a transfer).
  const canBank = banks.length > 0 && !tx.inflow && !left && !notYours
    && (tx.counts === 'spending' || tx.bank_id != null);
  const bank = banks.find((b) => b.id === tx.bank_id);

  const back = () => { setStep('main'); setError(null); };
  const body = {
    category: <ChangeCategory tx={tx} categories={categories} busy={busy} onBack={back}
                              onSave={(cat, always) => save(() => (
                                tx.category === 'Unsorted transfers'
                                  ? sortTransfers([tx.id], cat, false)
                                  : setCategory(tx.id, cat, always)))} />,
    split: <Split tx={tx} busy={busy} onBack={back}
                  onSave={(share) => save(() => setShare(tx.id, share))} />,
    note: <Note tx={tx} busy={busy} onBack={back}
                onSave={(note) => save(() => setTxNote(tx.id, note))} />,
    exclude: <Exclude tx={tx} busy={busy} onBack={back}
                      onSave={(reason) => save(() => excludeTransaction(tx.id, reason),
                                               { close: true })} />,
    bank: <PiggyBank tx={tx} banks={banks} busy={busy} onBack={back}
                     onSave={(bankId) => save(() => (bankId ? allocateToBank(Number(bankId), tx.id)
                                                              : unallocate(tx.id)))} />,
    whose: <Whose tx={tx} busy={busy} onBack={back}
                  onSave={(share, always) => save(async () => {
                    await setShare(tx.id, share);
                    if (always) await setMineAlways(tx.id, true);
                  })} />,
  }[step];

  return (
    <DetailPanel label={`${tx.merchant}, ${txAmount(tx.amount, { inflow: tx.inflow })}`}
                 overline="Transaction" onClose={onClose}>
      <div className="txd-hero">
        <Avatar name={tx.merchant} logo={tx.logo} large />
        <div className="txd-name">
          <h2 className="pk-h2">{tx.merchant}</h2>
          <span className="pk-label pk-muted">{longDate(tx.date)}</span>
        </div>
        <span className={`pk-h1 txd-amount${muted ? ' muted' : tx.inflow ? ' in' : ''}`}>
          {txAmount(tx.amount, { inflow: tx.inflow })}
        </span>
      </div>

      {error && <p className="txd-error" role="alert">{error.message}</p>}

      {body ?? (
        <>
          {tx.pending && <StatusPill>Pending · usually clears in 1–3 days</StatusPill>}

          <dl className="txd-details">
            <Detail label="Account" value={tx.account} />
            <Detail label="From your bank" value={tx.description} />
            <Detail label="Counts toward" value={tx.counts_toward} />
            {tx.note && !tx.note_link && <Detail label="Why" value={tx.note} />}
            {tx.split && <Detail label="Whole charge" value={txAmount(tx.full_amount)} />}
            {bank && <Detail label="Paid from" value={`${bank.name}${tx.bank_auto ? ' · automatically' : ''}`} />}
            {tx.my_note && <Detail label="Your note" value={tx.my_note} />}
          </dl>

          <section className="txd-category" aria-labelledby="txd-cat">
            <p className="pk-overline" id="txd-cat">Category</p>
            <div><CategoryChip label={tx.chip.label} suggested={tx.chip.suggested} /></div>
            {tx.suggested && <p className="txd-question">{suggestionReason(tx)}</p>}
          </section>

          <div className="txd-more">
            {canSplit && (
              <button type="button" className="txd-link" onClick={() => setStep('split')}>
                <PIcon name="users" size={18} /> Split this
              </button>
            )}
            {tx.joint && !left && (
              <button type="button" className="txd-link" onClick={() => setStep('whose')}>
                <PIcon name="users" size={18} /> Whose was it?
              </button>
            )}
            {canBank && (
              <button type="button" className="txd-link" onClick={() => setStep('bank')}>
                <PIcon name="target" size={18} />
                {bank ? 'Change piggy bank' : 'Pay from a piggy bank'}
              </button>
            )}
            <button type="button" className="txd-link" onClick={() => setStep('note')}>
              <PIcon name="info" size={18} /> {tx.my_note ? 'Edit note' : 'Add a note'}
            </button>
            {!left && (
              <button type="button" className="txd-link" onClick={() => setStep('exclude')}>
                <PIcon name="ban" size={18} /> Leave it out
              </button>
            )}
          </div>

          <div className="txd-actions">
            {left && (
              <PButton disabled={busy}
                       onClick={() => save(() => includeTransaction(tx.id), { close: true })}>
                Put it back
              </PButton>
            )}
            {notYours && (
              <PButton disabled={busy}
                       onClick={() => save(() => setShare(tx.id, tx.inflow ? -tx.full_amount
                                                                       : tx.full_amount),
                                           { close: true })}>
                It was mine
              </PButton>
            )}
            {canConfirm && (
              <PButton disabled={busy} onClick={() => save(() => confirmTx(tx.id), { close: true })}>
                Yes, that’s right
              </PButton>
            )}
            {!left && !notYours && (
              <PButton variant="secondary" disabled={busy} onClick={() => setStep('category')}>
                {tx.category === 'Unsorted transfers' ? 'Tell Pearl where it went'
                  : 'Change category'}
              </PButton>
            )}
          </div>
        </>
      )}
    </DetailPanel>
  );
}

function Detail({ label, value }) {
  return (
    <div className="txd-row">
      <dt>{label}</dt>
      <dd>{value || '—'}</dd>
    </div>
  );
}

/** A labelled control: the label names it, and nothing else does. */
function Field({ label, children }) {
  const id = useId();
  return (
    <div className="txd-field">
      <label className="pk-label" htmlFor={id}>{label}</label>
      {children(id)}
    </div>
  );
}

function Step({ title, onBack, children }) {
  return (
    <section className="txd-step" aria-label={title}>
      <button type="button" className="txd-link" onClick={onBack}>
        <PIcon name="arrowLeft" size={18} /> Back
      </button>
      <h3 className="pk-h3">{title}</h3>
      {children}
    </section>
  );
}

/** Interim for R-02: pick a category, optionally for every one from here. */
function ChangeCategory({ tx, categories, busy, onBack, onSave }) {
  const unsorted = tx.category === 'Unsorted transfers';
  const names = categories.map((c) => c.name)
    .filter((n) => n !== 'Unsorted transfers' && (!unsorted || n !== 'Transfers'));
  const [pick, setPick] = useState(unsorted ? 'Saved' : tx.category);
  const [always, setAlways] = useState(false);
  return (
    <Step title={unsorted ? 'Where did it go?' : 'Change category'} onBack={onBack}>
      <Field label="Category">
        {(id) => (
          <select id={id} value={pick} onChange={(e) => setPick(e.target.value)}>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        )}
      </Field>
      {!unsorted && (
        <label className="txd-check">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          Always use this for {tx.merchant}
        </label>
      )}
      <PButton disabled={busy || (!unsorted && pick === tx.category && !always)}
               onClick={() => onSave(pick, always)}>Save</PButton>
    </Step>
  );
}

/** Interim for S-01 (THL-124): how much of this was hers. */
function Split({ tx, busy, onBack, onSave }) {
  const [value, setValue] = useState(tx.split ? String(tx.amount) : '');
  const n = Number(value);
  const ok = value !== '' && n >= 0 && n <= tx.full_amount;
  return (
    <Step title="Split this" onBack={onBack}>
      <p className="pk-muted">Only your share counts toward your spending and your safe-to-spend.
        The whole charge was {txAmount(tx.full_amount)}.</p>
      <Field label="Your share">
        {(id) => (
          <input id={id} type="number" inputMode="decimal" min="0" step="0.01"
                 max={tx.full_amount} value={value} onChange={(e) => setValue(e.target.value)} />
        )}
      </Field>
      <div className="txd-quick">
        {[2, 3, 4].map((k) => (
          <button key={k} type="button" className="pk-filter"
                  onClick={() => setValue((tx.full_amount / k).toFixed(2))}>
            Split {k} ways
          </button>
        ))}
      </div>
      <PButton disabled={busy || !ok} onClick={() => onSave(n)}>Save</PButton>
      {tx.split && (
        <PButton variant="text" disabled={busy} onClick={() => onSave(null)}>
          It was all mine
        </PButton>
      )}
    </Step>
  );
}

function Note({ tx, busy, onBack, onSave }) {
  const [value, setValue] = useState(tx.my_note || '');
  return (
    <Step title={tx.my_note ? 'Edit note' : 'Add a note'} onBack={onBack}>
      <Field label="Note · only you can see this">
        {(id) => (
          <>
            <textarea id={id} rows={3} maxLength={NOTE_MAX} value={value}
                      onChange={(e) => setValue(e.target.value)} />
            <span className="pk-label pk-muted txd-count" aria-live="polite">
              {value.length}/{NOTE_MAX}
            </span>
          </>
        )}
      </Field>
      <PButton disabled={busy} onClick={() => onSave(value.trim())}>Save</PButton>
    </Step>
  );
}

function Exclude({ tx, busy, onBack, onSave }) {
  const [reason, setReason] = useState('');
  return (
    <Step title="Leave it out" onBack={onBack}>
      <p className="pk-muted">It won’t count anywhere: not in spending, income or your
        safe-to-spend. To put it back, choose Left out in the category filter.</p>
      <Field label="Why? (e.g. a work expense)">
        {(id) => (
          <input id={id} type="text" value={reason} maxLength={80}
                 onChange={(e) => setReason(e.target.value)} />
        )}
      </Field>
      <PButton disabled={busy || !reason.trim()} onClick={() => onSave(reason.trim())}>
        Leave out {tx.merchant}
      </PButton>
    </Step>
  );
}

/** A piggy bank pays for this charge instead of the month (or stops paying). */
function PiggyBank({ tx, banks, busy, onBack, onSave }) {
  const [pick, setPick] = useState(tx.bank_id == null ? '' : String(tx.bank_id));
  return (
    <Step title="Pay from a piggy bank" onBack={onBack}>
      <p className="pk-muted">A charge a piggy bank pays for leaves your week and your month:
        the bank’s monthly contribution already paid for it.</p>
      <Field label="Piggy bank">
        {(id) => (
          <select id={id} value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">None · count it as everyday spending</option>
            {banks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} · {b.available >= 0 ? `${money(b.available)} left` : `${money(-b.available)} over`}
              </option>
            ))}
          </select>
        )}
      </Field>
      <PButton disabled={busy || pick === (tx.bank_id == null ? '' : String(tx.bank_id))}
               onClick={() => onSave(pick)}>Save</PButton>
    </Step>
  );
}

/** On a joint account: whose was it, all or part. */
function Whose({ tx, busy, onBack, onSave }) {
  const sign = tx.inflow ? -1 : 1;
  const full = tx.full_amount;
  const mine = tx.share_set && Math.abs(tx.amount - full) < 0.005;
  const theirs = !tx.share_set || tx.amount < 0.005;
  const [mode, setMode] = useState(mine ? 'mine' : theirs ? 'theirs' : 'part');
  const [part, setPart] = useState(!mine && !theirs ? String(tx.amount) : '');
  const [always, setAlways] = useState(false);
  const n = Number(part);
  return (
    <Step title="Whose was it?" onBack={onBack}>
      <p className="pk-muted">On a joint account a transaction is {tx.joint}’s until you say
        it was yours. Only your part counts.</p>
      <div className="txd-quick" role="radiogroup" aria-label="Whose was it">
        {[['mine', 'Mine'], ['theirs', `${tx.joint}’s`], ['part', 'Part of it']].map(([k, l]) => (
          <button key={k} type="button" role="radio" aria-checked={mode === k}
                  className={`pk-filter${mode === k ? ' active' : ''}`} onClick={() => setMode(k)}>
            {l}
          </button>
        ))}
      </div>
      {mode === 'part' && (
        <Field label="Your part">
          {(id) => (
            <input id={id} type="number" inputMode="decimal" min="0" step="0.01" max={full}
                   value={part} onChange={(e) => setPart(e.target.value)} />
          )}
        </Field>
      )}
      {mode === 'mine' && !tx.inflow && (
        <label className="txd-check">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          Always mine at {tx.merchant}
        </label>
      )}
      <PButton disabled={busy || (mode === 'part' && !(n > 0 && n <= full))}
               onClick={() => onSave(mode === 'mine' ? sign * full : mode === 'theirs' ? null
                                     : sign * n, mode === 'mine' && always)}>
        Save
      </PButton>
    </Step>
  );
}

/**
 * Add a transaction by hand: cash, or a card that can't be connected. The
 * server checks it against what's already there; a likely duplicate is shown
 * and has to be confirmed as a different purchase.
 */
export function AddTransaction({ categories, onClose, onSaved }) {
  const today = new Date();
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const [draft, setDraft] = useState({ date: iso, description: '', amount: '', category: '' });
  const [conflict, setConflict] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => { setConflict(null); setDraft({ ...draft, [k]: e.target.value }); };
  const ok = draft.description.trim() && Number(draft.amount) > 0 && draft.date;

  async function submit(confirm = false) {
    setBusy(true);
    setError(null);
    try {
      const r = await addTransaction({ ...draft, amount: Number(draft.amount), confirm });
      if (r.conflict) setConflict(r);
      else onSaved?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <DetailPanel label="Add a transaction" overline="Add a transaction" onClose={onClose}>
      <h2 className="pk-h2">What did you spend?</h2>
      <form className="txd-step" onSubmit={(e) => { e.preventDefault(); if (ok) submit(false); }}>
        <Field label="What was it?">
          {(id) => <input id={id} type="text" required value={draft.description}
                          onChange={set('description')} maxLength={80} />}
        </Field>
        <Field label="Amount">
          {(id) => <input id={id} type="number" inputMode="decimal" min="0.01" step="0.01"
                          required value={draft.amount} onChange={set('amount')} />}
        </Field>
        <Field label="Date">
          {(id) => <input id={id} type="date" required value={draft.date} onChange={set('date')} />}
        </Field>
        <Field label="Category">
          {(id) => (
            <select id={id} value={draft.category} onChange={set('category')}>
              <option value="">Let Pearl suggest one</option>
              {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          )}
        </Field>
        {error && <p className="txd-error" role="alert">{error.message}</p>}
        {conflict ? (
          <div className="txd-step" role="status">
            <p>{conflict.duplicate ? conflict.error
              : 'This looks like something already in your transactions:'}</p>
            <dl className="txd-details">
              {(conflict.matches ?? []).map((m) => (
                <Detail key={m.id} label={`${m.merchant} · ${longDate(m.date)}`}
                        value={txAmount(m.amount)} />
              ))}
            </dl>
            {!conflict.duplicate && (
              <PButton disabled={busy} onClick={() => submit(true)}>
                It’s a different purchase · add it
              </PButton>
            )}
          </div>
        ) : (
          <PButton type="submit" disabled={busy || !ok}>Add it</PButton>
        )}
      </form>
    </DetailPanel>
  );
}
