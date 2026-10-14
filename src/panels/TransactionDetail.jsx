import { useEffect, useId, useState } from 'react';
import {
  Alert, Avatar, CategoryChip, Choice, DetailPanel, PButton, StatusPill, txAmount,
} from '../pearl/kit.jsx';
import { depositChoices } from './joint.js';
import PIcon from '../pearl/icons.jsx';
import CategoryPicker, { categoryLabel } from './CategoryPicker.jsx';
import { LinkToSplit, RepaymentQuestion, SplitSummary, SplitThis } from './Splits.jsx';
import {
  addTransaction, allocateToBank, confirmTx, excludeTransaction, getBanks, getTx,
  includeTransaction, money, setCategory, setJointFrom, setMineAlways, setParty, setShare,
  setTxNote,
  sortTransfers,
  unallocate, setSplit, clearSplit, unlinkPayback, linkPayback, setOneOff,
} from '../api.js';
import './txextras.css';

/**
 * One transaction (Pearl TX-04, THL-122): a 560px panel over the list, the
 * whole page on a phone.
 *
 * A suggested category asks "Is it right?": yes confirms it and closes with
 * "Saved"; once confirmed the question and the button go and only Change
 * category stays. Change category (R-02, THL-123) takes the panel over, with a
 * back link to the transaction; saving closes it with a toast that says what
 * changed and offers Undo (R-03).
 *
 * A row that counts can be marked a one-off (THL-71 U-01, U-03; `OneOffCard`).
 */

const NOTE_MAX = 140;
// The list's note for a one-off; the one-off card says it here instead.
const ONE_OFF_NOTE = 'Unusual · left out of your usual month';
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

  async function save(fn, { close = false, change } = {}) {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      onSaved?.({ close, change: change?.(res) });
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
  // A change that moved a number closes the panel with what it did (R-03).
  const changed = (verb, cat) => (res) => ({
    id: tx.id,
    title: [`${verb} ${categoryLabel(cat)}.`, res?.impact?.title].filter(Boolean).join(' '),
    detail: res?.impact?.detail ?? '',
    undo: res?.undo,
  });

  if (step === 'category') {
    const unsorted = tx.category === 'Unsorted transfers';
    return (
      <DetailPanel label="Change category" onClose={onClose}
                   back={{ label: `${tx.merchant} · ${txAmount(tx.amount, { inflow: tx.inflow })}`,
                           onClick: back }}>
        <h2 className="pk-h2">{unsorted ? 'Where did this go?' : 'Change category'}</h2>
        {error && <p className="txd-error" role="alert">{error.message}</p>}
        <CategoryPicker tx={tx} categories={categories} busy={busy}
                        onSave={(cat, always) => save(() => (
                          unsorted ? sortTransfers([tx.id], cat, false)
                            : setCategory(tx.id, cat, always)),
                        { close: true, change: changed(unsorted ? 'Sorted as' : 'Moved to', cat) })} />
      </DetailPanel>
    );
  }

  if (step === 'split') {
    return (
      <DetailPanel label="Split this" onClose={onClose}
                   back={{ label: `${tx.merchant} · ${txAmount(tx.full_amount)}`, onClick: back }}>
        <h2 className="pk-h2">Split this</h2>
        {error && <p className="txd-error" role="alert">{error.message}</p>}
        <SplitThis tx={tx} busy={busy}
                   onSave={(split) => save(() => setSplit(tx.id, split))}
                   onClear={() => save(() => clearSplit(tx.id))} />
      </DetailPanel>
    );
  }

  // Money in that pays back a split (S-02, S-03).
  const linked = (o) => () => {
    const owed = Math.round((o.owes - tx.full_amount) * 100) / 100;
    return {
      id: tx.id,
      title: `Linked to ${o.merchant}.`,
      detail: owed > 0.004 ? `${o.name} still owes ${txAmount(owed)}. It won’t count as income.`
        : `${o.name}’s share is paid back. It won’t count as income.`,
    };
  };
  const link = (o) => save(() => linkPayback(o.charge_id, tx.id, o.name),
                           { close: true, change: linked(o) });

  if (step === 'link') {
    return (
      <DetailPanel label="Which split is this for?" onClose={onClose}
                   back={{ label: `${tx.merchant} · ${txAmount(tx.amount, { inflow: tx.inflow })}`,
                           onClick: back }}>
        <h2 className="pk-h2">Which split is this for?</h2>
        {error && <p className="txd-error" role="alert">{error.message}</p>}
        <LinkToSplit tx={tx} busy={busy} onLink={link} onNone={() => setStep('category')} />
      </DetailPanel>
    );
  }

  const match = !left && tx.repayment?.suggestion;
  const otherSplits = !left && !match && (tx.repayment?.splits?.length ?? 0) > 0;

  const body = {
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
    party: <Party tx={tx} busy={busy} onBack={back}
                  onSave={(name) => save(() => setParty(tx.id, name))} />,
    from: <JointFrom tx={tx} busy={busy} onBack={back}
                     onSave={(who, remember, person) => save(() => setJointFrom(tx.id, who, remember, person))} />,
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
        <span className={`txd-amount${muted ? ' muted' : tx.inflow ? ' in' : ''}`}>
          <span className="pk-h1">{txAmount(tx.amount, { inflow: tx.inflow })}</span>
          {tx.split && (
            <span className="pk-label pk-muted txd-sub">your share of {txAmount(tx.full_amount)}</span>
          )}
        </span>
      </div>

      {error && <p className="txd-error" role="alert">{error.message}</p>}

      {body ?? (
        <>
          {tx.pending && <StatusPill>Pending · usually clears in 1–3 days</StatusPill>}
          {tx.one_off && (
            <span className="txd-pill"><StatusPill icon={null} tone="neutral">
              Unusual · not in your averages
            </StatusPill></span>
          )}

          {tx.splitting && <SplitSummary tx={tx} onEdit={() => setStep('split')} />}

          {match && (
            <>
              <RepaymentQuestion match={match} />
              <button type="button" className="txd-link" onClick={() => setStep('link')}>
                It’s for a different split
              </button>
            </>
          )}

          <dl className="txd-details">
            <Detail label="Account" value={tx.account} />
            <Detail label="From your bank" value={tx.description} />
            <Detail label="Counts toward" value={tx.counts_toward} />
            {tx.note && !tx.note_link && !(tx.one_off && tx.note === ONE_OFF_NOTE)
              && <Detail label="Why" value={tx.note} />}
            {tx.split && <Detail label="Whole charge" value={txAmount(tx.full_amount)} />}
            {tx.repays_charge && (
              <Detail label="Pays back"
                      value={`${tx.repays_charge.merchant}${tx.repays_charge.person ? ` · ${tx.repays_charge.person}’s share` : ''} · not income`} />
            )}
            {(tx.repaid_by ?? []).map((r) => (
              <Detail key={r.id} label="Repayment"
                      value={`${r.merchant} · ${txAmount(-r.amount)} · not income`} />
            ))}
            {bank && <Detail label="Paid from" value={`${bank.name}${tx.bank_auto ? ' · automatically' : ''}`} />}
            {tx.my_note && <Detail label="Your note" value={tx.my_note} />}
          </dl>

          {tx.can_one_off && !left && (
            <OneOffCard tx={tx} busy={busy}
                        onToggle={() => save(() => setOneOff(tx.id, !tx.one_off), {
                          close: true,
                          change: (res) => ({ id: tx.id, title: res.title, detail: res.detail,
                                              undo: res.undo }),
                        })} />
          )}

          <section className="txd-category" aria-labelledby="txd-cat">
            <p className="pk-overline" id="txd-cat">Category</p>
            <div><CategoryChip label={tx.chip.label} suggested={tx.chip.suggested} /></div>
            {tx.suggested && <p className="txd-question">{suggestionReason(tx)}</p>}
          </section>

          <div className="txd-more">
            {canSplit && !tx.splitting && (
              <button type="button" className="txd-link" onClick={() => setStep('split')}>
                <PIcon name="users" size={18} /> Split this
              </button>
            )}
            {otherSplits && (
              <button type="button" className="txd-link" onClick={() => setStep('link')}>
                <PIcon name="users" size={18} /> Pays back a split?
              </button>
            )}
            {tx.repays_charge && (
              <button type="button" className="txd-link"
                      onClick={() => save(() => unlinkPayback(tx.repays_charge.id, tx.id))}>
                <PIcon name="x" size={18} /> Unlink repayment
              </button>
            )}
            {(tx.repaid_by ?? []).map((r) => (
              <button key={r.id} type="button" className="txd-link"
                      onClick={() => save(() => unlinkPayback(tx.id, r.id))}>
                <PIcon name="x" size={18} />
                {tx.repaid_by.length === 1 ? 'Unlink repayment'
                  : `Unlink ${r.merchant} · ${txAmount(-r.amount)}`}
              </button>
            ))}
            {tx.etransfer && (
              <button type="button" className="txd-link" onClick={() => setStep('party')}>
                <PIcon name="user" size={18} />
                {partyTitle(tx.etransfer)}
              </button>
            )}
            {tx.joint && !left && tx.inflow && (
              <button type="button" className="txd-link" onClick={() => setStep('from')}>
                <PIcon name="users" size={18} /> Who put this in?
              </button>
            )}
            {tx.joint && !left && !tx.inflow && (
              <button type="button" className="txd-link" onClick={() => setStep('whose')}>
                <PIcon name="users" size={18} /> Whose was it?
              </button>
            )}
            {canBank && (
              <button type="button" className="txd-link" onClick={() => setStep('bank')}>
                <PIcon name="target" size={18} />
                {bank ? 'Change treasure chest' : 'Pay from a treasure chest'}
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
                       // Back to the joint default: hers, less what they put in.
                       onClick={() => save(() => setShare(tx.id, tx.joint ? null
                         : tx.inflow ? -tx.full_amount : tx.full_amount), { close: true })}>
                It was mine
              </PButton>
            )}
            {match && (
              <>
                <PButton disabled={busy} onClick={() => link(match)}>Yes, link them</PButton>
                <PButton variant="secondary" disabled={busy} onClick={() => setStep('category')}>
                  No, it’s something else
                </PButton>
              </>
            )}
            {canConfirm && !match && (
              <PButton disabled={busy} onClick={() => save(() => confirmTx(tx.id), { close: true })}>
                Yes, that’s right
              </PButton>
            )}
            {!left && !notYours && !match && (
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

/**
 * "This was a one-off" (Pearl THL-71, U-01 and U-03). Ticked, it is left out
 * of her usual month, projections and trend suggestions, and still counts in
 * its own month and in safe to spend. Ticking closes the panel with a toast
 * that names the average it moved (U-02); unticking puts it back the same way.
 */
export function OneOffCard({ tx, busy = false, onToggle }) {
  const month = MONTHS[Number(tx.date.slice(5, 7)) - 1];
  return (
    <section className="txd-oneoff" aria-label="One-off">
      <Choice type="checkbox" checked={!!tx.one_off} disabled={busy} onChange={onToggle}
              label="This was a one-off"
              description={`Leave it out of my usual month. It still counts in ${month}.`} />
      <p>{tx.one_off ? (tx.one_off_line?.line || 'Left out of your usual month.')
        : 'Good for tax refunds, moving costs or a big one-time purchase.'}</p>
    </section>
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

/** "Who sent this?", or "Change who it was from" once there's a name. */
export function partyTitle(et) {
  if (!et.name) return et.direction === 'from' ? 'Who sent this?' : 'Who was it to?';
  return `Change who it was ${et.direction}`;
}

/** An e-Transfer's person, when the bank didn't name them (THL-122). */
function Party({ tx, busy, onBack, onSave }) {
  const et = tx.etransfer;
  const [name, setName] = useState(et.named_by === 'you' ? et.name : '');
  return (
    <Step title={partyTitle(et)} onBack={onBack}>
      <p className="pk-muted">
        {et.name && et.named_by === 'bank' ? `Your bank says ${et.name}.`
          : et.named_by === 'you' ? 'You named them.'
            : 'Your bank didn’t say. Naming them helps match repayments to splits.'}
      </p>
      <Field label={et.direction === 'from' ? 'Who sent it' : 'Who it went to'}>
        {(id) => (
          <input id={id} type="text" value={name} maxLength={60} autoComplete="off"
                 placeholder="First and last name" onChange={(e) => setName(e.target.value)} />
        )}
      </Field>
      <PButton disabled={busy || !name.trim()} onClick={() => onSave(name.trim())}>Save</PButton>
      {et.named_by === 'you' && (
        <PButton variant="text" disabled={busy} onClick={() => onSave('')}>
          Use your bank’s name instead
        </PButton>
      )}
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

/**
 * Pay from a treasure chest (Pearl G-07, THL-179): a chest pays for this
 * charge instead of the month, or stops paying. Each chest says what is in
 * it, and the choice says what it does to safe to spend before it is saved.
 */
function PiggyBank({ tx, banks, busy, onBack, onSave }) {
  const current = tx.bank_id == null ? '' : String(tx.bank_id);
  const [pick, setPick] = useState(current);
  const charge = money(tx.bank_amount || tx.amount, { cents: true });
  const chosen = banks.find((b) => String(b.id) === pick);
  const was = banks.find((b) => String(b.id) === current);
  let effect = null;
  if (pick !== current) {
    effect = chosen
      ? (was ? `It’ll come out of ${chosen.name} instead of ${was.name}.`
        : `It’ll come out of ${chosen.name}, so safe to spend goes up by ${charge}.`)
      : `It’ll go back into your month, so safe to spend goes down by ${charge}.`;
  }
  return (
    <Step title="Pay from a treasure chest" onBack={onBack}>
      <div className="pk-choices" role="radiogroup" aria-label="Pay from a treasure chest">
        <Choice name="chest" checked={pick === ''} onChange={() => setPick('')}
                label="Don’t use a chest" />
        {banks.map((b) => (
          <Choice key={b.id} name="chest" checked={pick === String(b.id)}
                  onChange={() => setPick(String(b.id))} label={b.name}
                  description={`${money(Math.max(b.held ?? b.available, 0))} in the chest`} />
        ))}
      </div>
      {effect && <Alert>{effect}</Alert>}
      <PButton disabled={busy || pick === current} onClick={() => onSave(pick)}>Save</PButton>
    </Step>
  );
}

/**
 * A charge on a joint account: hers by default, less what the other person
 * put in that month (finance/joint.py); or all theirs, or a part she says.
 */
function Whose({ tx, busy, onBack, onSave }) {
  const full = tx.full_amount;
  const theirs = tx.share_set && tx.amount < 0.005;
  const part = tx.share_set && !theirs && Math.abs(tx.amount - full) >= 0.005;
  const [mode, setMode] = useState(theirs ? 'theirs' : part ? 'part' : 'mine');
  const [amount, setAmount] = useState(part ? String(tx.amount) : '');
  const [always, setAlways] = useState(false);
  const n = Number(amount);
  return (
    <Step title="Whose was it?" onBack={onBack}>
      <p className="pk-muted">On a joint account, spending is yours, less what {tx.joint} puts
        in that month. Only your part counts.</p>
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
                   value={amount} onChange={(e) => setAmount(e.target.value)} />
          )}
        </Field>
      )}
      {mode === 'mine' && (
        <label className="txd-check">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          Always all mine at {tx.merchant}
        </label>
      )}
      <PButton disabled={busy || (mode === 'part' && !(n > 0 && n <= full))}
               onClick={() => onSave(mode === 'mine' ? null : mode === 'theirs' ? 0 : n,
                                     mode === 'mine' && always)}>
        Save
      </PButton>
    </Step>
  );
}

/** Money into a joint account from outside: hers, or the other person's. */
function JointFrom({ tx, busy, onBack, onSave }) {
  const choices = depositChoices(tx.joint_people, tx.joint);
  const start = tx.joint_from === 'me' ? 'me'
    : tx.joint_from === 'them' ? (tx.joint_person ? `p:${tx.joint_person}` : 'them') : '';
  const [pick, setPick] = useState(choices.some((c) => c.value === start) ? start : '');
  const [remember, setRemember] = useState(true);
  const chosen = choices.find((c) => c.value === pick);
  return (
    <Step title="Who put this in?" onBack={onBack}>
      <p className="pk-muted">It came into your account with {tx.joint} from outside Pearl.</p>
      <div className="pk-choices" role="radiogroup" aria-label="Who put this in?">
        {choices.map((c) => (
          <Choice key={c.value} name="joint-from" checked={pick === c.value}
                  onChange={() => setPick(c.value)} label={c.label} description={c.description} />
        ))}
      </div>
      <label className="txd-check">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        The same for every deposit from {tx.merchant}
      </label>
      <PButton disabled={busy || !chosen}
               onClick={() => onSave(chosen.who, remember, chosen.person)}>Save</PButton>
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
