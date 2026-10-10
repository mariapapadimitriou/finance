import { useEffect, useId, useState } from 'react';
import {
  Avatar, CategoryChip, DetailPanel, PButton, StatusPill, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import {
  confirmTx, excludeTransaction, getTx, includeTransaction, setCategory, setShare, setTxNote,
  sortTransfers,
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
  const [step, setStep] = useState('main');      // main | category | split | note | exclude
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getTx(id).then((r) => { if (live) setTx(r); }).catch((e) => { if (live) setError(e); });
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
  const canConfirm = tx.suggested && tx.category !== 'Unsorted transfers' && !left;
  const canSplit = tx.counts === 'spending' && !tx.inflow && !left;

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
            {canConfirm && (
              <PButton disabled={busy} onClick={() => save(() => confirmTx(tx.id), { close: true })}>
                Yes, that’s right
              </PButton>
            )}
            {!left && (
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
