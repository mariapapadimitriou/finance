import { useEffect, useMemo, useState } from 'react';
import {
  addBill, addPay, answerPay, answerRent, confirmBills, editBill, editPay, getIncomeBills,
  money, removeBill, saveExpected, skipExpected,
} from '../api.js';
import { ActionToast, Alert, Choice, StatTile } from './kit.jsx';
import PIcon from './icons.jsx';
import { AuthLayout, Banner, Field, Heading, Initials, MARKS } from './ui.jsx';

/**
 * Income and recurring bills, confirmed (Pearl THL-45; designed in THL-127,
 * Figma "Income and recurring bills · THL-127", I-01 to I-06).
 *
 *   I-01 Is this your paycheque?   the strongest pay candidate, the rest as
 *                                  "Also this?"; repayments and friends'
 *                                  e-Transfers are never candidates
 *   I-02 Edit your pay             "The amount or timing is off", or another source
 *   I-03 No pay found              the income she expects each month
 *   I-04 Are these your regular bills?  rent by e-Transfer asked about first
 *   I-05 Add or edit a bill
 *   I-06 All set                   income and bills each month
 *
 * Runs after a bank is linked in onboarding (between O-11 and O-12) and again
 * from Profile › Income and bills. The forms (PayForm, ExpectedForm,
 * BillForm) and the bill row are shared with that page. Done in under two
 * minutes: every screen is one decision with the answer already filled in.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const parts = (iso) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return { y, m, d, weekday: WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] };
};
/** "Oct 2". */
export const shortDay = (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1].slice(0, 3)} ${p.d}`; };
/** "1st", "12th", "22nd". */
export const ordinal = (n) => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

export const PAY_OPTIONS = [
  { value: 'weekly', label: 'Every week' },
  { value: 'biweekly', label: 'Every 2 weeks' },
  { value: 'semimonthly', label: 'Twice a month' },
  { value: 'monthly', label: 'Every month' },
  { value: 'irregular', label: 'It varies' },
];
export const BILL_OPTIONS = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every 2 weeks' },
  { value: 'bimonthly', label: 'Every 2 months' },
  { value: 'quarterly', label: 'Every 3 months' },
  { value: 'semiannual', label: 'Every 6 months' },
  { value: 'annual', label: 'Yearly' },
];
const BILL_WORDS = Object.fromEntries(BILL_OPTIONS.map((o) => [o.value, o.label]));

/** How often pay comes, in words: "every second Friday". */
export function payWhen(pay) {
  const day = pay.last || pay.next ? parts(pay.last || pay.next) : null;
  switch (pay.cadence) {
    case 'weekly': return day ? `every ${day.weekday}` : 'every week';
    case 'biweekly': return day ? `every second ${day.weekday}` : 'every 2 weeks';
    case 'semimonthly': return 'twice a month';
    case 'monthly': return day ? `monthly, around the ${ordinal(day.d)}` : 'monthly';
    default: return 'when it comes';
  }
}

/** I-01's line under the payer: "$2,150.00 · every second Friday · last on Oct 2". */
export function payMeta(pay) {
  return [money(pay.amount, { cents: true }), payWhen(pay),
    pay.last ? `last on ${shortDay(pay.last)}` : pay.next ? `next on ${shortDay(pay.next)}` : null]
    .filter(Boolean).join(' · ');
}

/** A bill's schedule: "Monthly · around the 12th", "Every 2 months · amount varies". */
export function billSchedule(b) {
  const how = BILL_WORDS[b.cadence] ?? 'Regularly';
  if (b.cadence === 'monthly') {
    return [how, b.day ? `around the ${ordinal(b.day)}` : null, b.varies ? 'amount varies' : null]
      .filter(Boolean).join(' · ');
  }
  return [how, b.varies ? 'amount varies' : b.next ? `next on ${shortDay(b.next)}` : null]
    .filter(Boolean).join(' · ');
}

/** "$85.00", or "about $60" when it varies. */
export const billAmount = (b) => (b.varies ? `about ${money(Math.round(b.amount))}` : money(b.amount, { cents: true }));

/** A whole-dollar figure for I-06, never "$0". */
const tile = (n, none) => (n > 0 ? money(Math.round(n)) : none);

/** Parse what someone typed as money: "$2,150" → 2150. */
const parseMoney = (text) => {
  const clean = String(text ?? '').replace(/[$,\s]/g, '');
  return /^\d+(\.\d{1,2})?$/.test(clean) ? Number(clean) : NaN;
};

/** I-04's rent question (only when the pattern exists). */
export const rentWords = (q) => `Your ${money(Math.round(q.amount))} e-Transfer to ${q.recipient} goes out around the ${ordinal(q.day)} every month. Is it your rent?`;

/** Bill row (Handoff "Bill row"): the checkbox says whether it counts. */
export function BillRow({ bill, ticked, onTick, onEdit }) {
  return (
    <div className={`ib-row${ticked ? '' : ' off'}`}>
      <label className="ib-tick">
        <input type="checkbox" checked={ticked} onChange={(e) => onTick(e.target.checked)}
               aria-label={`Count ${bill.name} as a regular bill`} />
        <span className="ib-box" aria-hidden="true">{ticked && <PIcon name="check" size={16} />}</span>
      </label>
      <span className="ib-row-text">
        <span>{bill.name}</span>
        <small>{billSchedule(bill)}</small>
      </span>
      <span className="ib-amt">{billAmount(bill)}</span>
      <button type="button" className="ib-edit" onClick={onEdit}
              aria-label={`Edit ${bill.name}`}>Edit</button>
    </div>
  );
}

/** I-01's deposit: who paid, how much and how often, and why it looks like pay. */
export function PayRow({ pay, chip = 'Looks like pay' }) {
  return (
    <div className="p-account ib-pay">
      <Initials name={pay.name} large />
      <div className="p-account-text">
        <span>{pay.name}</span>
        <small>{payMeta(pay)}</small>
      </div>
      {chip && <span className="p-chip"><PIcon name="check" /> {chip}</span>}
    </div>
  );
}

function Select({ value, onChange, options, ...p }) {
  return (
    <>
      <select {...p} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <PIcon name="chevronDown" className="p-chevron" />
    </>
  );
}

/** I-02: name, usual amount after tax, how often, next pay date. */
export function PayForm({ pay, title = 'Tell us about your pay', eyebrow = 'Your money coming in',
                          onSave, onCancel }) {
  const [name, setName] = useState(pay?.name ?? '');
  const [amount, setAmount] = useState(pay?.amount ? money(pay.amount, { cents: true }) : '');
  const [cadence, setCadence] = useState(pay?.cadence ?? 'biweekly');
  const [next, setNext] = useState(pay?.next ?? '');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const n = parseMoney(amount);
    if (!name.trim()) { setError({ field: 'name', text: 'Give your pay a name, like your employer.' }); return; }
    if (!(n > 0)) { setError({ field: 'amount', text: 'Enter what lands in your account, like 2150.' }); return; }
    if (cadence !== 'irregular' && !next) { setError({ field: 'next', text: 'Choose your next pay date.' }); return; }
    setError(null);
    setBusy(true);
    onSave({ name: name.trim(), amount: n, cadence, next: next || null, payer: pay?.payer ?? '' })
      .catch((err) => setError({ field: 'name', text: err.message }))
      .finally(() => setBusy(false));
  };
  const err = (f) => (error?.field === f ? error.text : null);
  return (
    <form className="ib-form" onSubmit={submit} noValidate>
      <Heading eyebrow={eyebrow} title={title} />
      <Field label="Name" error={err('name')}>
        {(p) => <input {...p} value={name} autoComplete="off" placeholder="Your employer"
                       onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Usual amount after tax" hint="Use what lands in your account." error={err('amount')}>
        {(p) => <input {...p} value={amount} inputMode="decimal" autoComplete="off" placeholder="$2,150.00"
                       onChange={(e) => setAmount(e.target.value)} />}
      </Field>
      <Field label="How often">
        {(p) => <Select {...p} value={cadence} onChange={setCadence} options={PAY_OPTIONS} />}
      </Field>
      <Field label={cadence === 'irregular' ? 'Next pay date (optional)' : 'Next pay date'} error={err('next')}>
        {(p) => <input {...p} type="date" value={next} onChange={(e) => setNext(e.target.value)} />}
      </Field>
      <div className="p-actions">
        <button type="submit" className="p-btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        <button type="button" className="p-btn text" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** I-03: the income she expects each month, after tax. */
export function ExpectedForm({ expected, onSave, onSkip, skipLabel = 'Skip for now',
                               eyebrow = 'Your money coming in',
                               title = 'We didn’t spot a regular paycheque',
                               sub = 'That’s common if you’re new to a job, freelance, or paid in cash. Tell us roughly what you expect.' }) {
  const [amount, setAmount] = useState(expected?.amount ? money(expected.amount) : '');
  const [varies, setVaries] = useState(!!expected?.varies);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const n = parseMoney(amount);
    if (!(n > 0)) { setError('Enter what you expect each month after tax, like 3800.'); return; }
    setError(null);
    setBusy(true);
    onSave(n, varies).catch((err) => setError(err.message)).finally(() => setBusy(false));
  };
  return (
    <form className="ib-form" onSubmit={submit} noValidate>
      <Heading eyebrow={eyebrow} title={title} sub={sub} />
      <Field label="Expected income each month" hint="After tax. A rough number is fine." error={error}>
        {(p) => <input {...p} value={amount} inputMode="decimal" autoComplete="off" placeholder="$3,800"
                       onChange={(e) => setAmount(e.target.value)} />}
      </Field>
      <div className="ib-choices">
        <Choice type="checkbox" checked={varies} onChange={setVaries}
                label="My income varies month to month"
                description="We’ll plan with a careful estimate" />
      </div>
      <div className="p-actions">
        <button type="submit" className="p-btn primary" disabled={busy}>{busy ? 'Saving…' : 'Continue'}</button>
        {onSkip && <button type="button" className="p-btn text" onClick={onSkip}>{skipLabel}</button>}
      </div>
    </form>
  );
}

/** I-05: name, amount, how often, next due date; editing adds "Remove this bill". */
export function BillForm({ bill, onSave, onCancel, onRemove, eyebrow = 'Your regular bills' }) {
  const [name, setName] = useState(bill?.name ?? '');
  const [amount, setAmount] = useState(bill?.amount ? money(bill.amount, { cents: true }) : '');
  const [cadence, setCadence] = useState(bill?.cadence ?? 'monthly');
  const [next, setNext] = useState(bill?.next ?? '');
  const [varies, setVaries] = useState(!!bill?.varies);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const n = parseMoney(amount);
    if (!name.trim()) { setError({ field: 'name', text: 'Give the bill a name.' }); return; }
    if (!(n > 0)) { setError({ field: 'amount', text: 'Enter the amount, like 45.' }); return; }
    if (!next) { setError({ field: 'next', text: 'Choose the next due date.' }); return; }
    setError(null);
    setBusy(true);
    onSave({ name: name.trim(), amount: n, cadence, next, varies })
      .catch((err) => setError({ field: 'name', text: err.message }))
      .finally(() => setBusy(false));
  };
  const err = (f) => (error?.field === f ? error.text : null);
  return (
    <form className="ib-form" onSubmit={submit} noValidate>
      <Heading eyebrow={eyebrow} title={bill ? 'Edit a bill' : 'Add a bill'} />
      <Field label="Name" error={err('name')}>
        {(p) => <input {...p} value={name} autoComplete="off" placeholder="Gym membership"
                       onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Amount" error={err('amount')}>
        {(p) => <input {...p} value={amount} inputMode="decimal" autoComplete="off" placeholder="$45.00"
                       onChange={(e) => setAmount(e.target.value)} />}
      </Field>
      <Field label="How often">
        {(p) => <Select {...p} value={cadence} onChange={setCadence} options={BILL_OPTIONS} />}
      </Field>
      <Field label="Next due date" error={err('next')}>
        {(p) => <input {...p} type="date" value={next} onChange={(e) => setNext(e.target.value)} />}
      </Field>
      <div className="ib-choices">
        <Choice type="checkbox" checked={varies} onChange={setVaries}
                label="The amount changes each time" />
      </div>
      <div className="p-actions">
        <button type="submit" className="p-btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save bill'}</button>
        <button type="button" className="p-btn text" onClick={onCancel}>Cancel</button>
        {bill && onRemove && (
          <button type="button" className="p-btn text" onClick={onRemove}>Remove this bill</button>
        )}
      </div>
    </form>
  );
}

/** Restores a removed bill: an added one is added again, a found one counted again. */
export function undoRemove(removed) {
  const { key, ...bill } = removed;
  return key.startsWith('added:') ? addBill(bill) : editBill(key, bill);
}

const PANELS = {
  income: { mark: 'closed', headline: 'Income first.',
            body: 'Knowing when you’re paid lets Pearl work out what’s Allowance.' },
  bills: { mark: 'closed', headline: 'Then what goes out.',
           body: 'Regular bills are set aside before anything counts as Allowance.' },
  done: { mark: 'opening', headline: 'Ready.',
          body: 'Pearl can now work out what’s Allowance each month.' },
};

/** Where the check starts: the paycheque if Pearl found one, else I-03. */
export const firstScreen = (d) => (d.candidates.length ? 'pay' : d.pays.length ? 'bills' : 'expected');

/**
 * The check, I-01 to I-06. `onDone` after I-06's Continue; `onDoc` opens the
 * footer's Privacy, Terms and Help.
 */
export default function IncomeBillsFlow({ onDone, onDoc, initial = null, start = null }) {
  const [data, setData] = useState(initial);
  const [screen, setScreen] = useState(() => (start ?? (initial ? firstScreen(initial) : null)));
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [choice, setChoice] = useState('yes');
  const [also, setAlso] = useState({});
  const [editingPay, setEditingPay] = useState(null);
  const [ticked, setTicked] = useState(
    () => (initial ? Object.fromEntries(initial.bills.map((b) => [b.key, b.ticked])) : null));
  const [editingBill, setEditingBill] = useState(null);
  const [removed, setRemoved] = useState(null);

  useEffect(() => {
    if (data) return;
    getIncomeBills().then((d) => {
      setData(d);
      setScreen((s) => s ?? firstScreen(d));
    }).catch((e) => setError(e.message));
  }, [data]);

  // I-04 starts from what Pearl or she decided; rows she adds come in ticked.
  useEffect(() => {
    if (!data) return;
    setTicked((t) => Object.fromEntries(data.bills.map((b) => [b.key, t?.[b.key] ?? b.ticked])));
  }, [data]);

  const step = (next) => { setHistory((h) => [...h, screen]); setScreen(next); setError(null); };
  const back = history.length ? () => {
    setScreen(history.at(-1)); setHistory((h) => h.slice(0, -1)); setError(null);
  } : null;
  const run = async (fn, next) => {
    setBusy(true);
    setError(null);
    try {
      const d = await fn();
      if (d) setData(d);
      if (next) step(typeof next === 'function' ? next(d) : next);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const layout = (panel, topRight, content, { centered = false, onBack = back } = {}) => (
    <AuthLayout {...PANELS[panel]} footnote={false} topRight={topRight} onBack={onBack}
                onDoc={onDoc} centered={centered}>
      {content}
    </AuthLayout>
  );

  if (!data || !screen) {
    return layout('income', '1 of 2', error ? <Banner tone="caution">{error}</Banner>
      : <p className="p-sub" role="status">Looking at what comes in…</p>);
  }

  const candidate = data.candidates[0];
  const extra = data.candidates.slice(1);

  // ── I-01 Is this your paycheque? ──────────────────────────────────────
  if (screen === 'pay' && candidate) {
    const next = async () => {
      if (choice === 'off') { setEditingPay(candidate); step('edit'); return; }
      await run(async () => {
        let d = await answerPay(candidate.payer, choice);
        for (const c of extra.filter((x) => also[x.payer])) d = await answerPay(c.payer, 'yes');
        return d;
      }, (d) => (choice === 'no' && !d.pays.length ? 'expected' : 'bills'));
    };
    return layout('income', '1 of 2', (
      <>
        <Heading eyebrow="Your money coming in" title="Is this your paycheque?"
                 sub="We found a deposit that looks like your pay." />
        <PayRow pay={candidate} />
        <div className="ib-choices" role="radiogroup" aria-label="Is this your pay?">
          <Choice name="ib-pay" checked={choice === 'yes'} onChange={() => setChoice('yes')}
                  label="Yes, that’s my pay" />
          <Choice name="ib-pay" checked={choice === 'off'} onChange={() => setChoice('off')}
                  label="The amount or timing is off" />
          <Choice name="ib-pay" checked={choice === 'no'} onChange={() => setChoice('no')}
                  label="No, it’s something else" />
        </div>
        {extra.length > 0 && (
          <div className="ib-choices">
            <p className="p-eyebrow ib-muted">Also this?</p>
            {extra.map((c) => (
              <Choice key={c.payer} type="checkbox" checked={!!also[c.payer]}
                      onChange={(v) => setAlso((a) => ({ ...a, [c.payer]: v }))}
                      label={c.name} description={payMeta(c)} />
            ))}
          </div>
        )}
        <button type="button" className="p-link ib-add" onClick={() => { setEditingPay(null); step('edit'); }}>
          + Add another source of income
        </button>
        {error && <Banner tone="caution">{error}</Banner>}
        <div className="p-actions">
          <button type="button" className="p-btn primary" disabled={busy} onClick={next}>Continue</button>
        </div>
      </>
    ), { onBack: back });
  }

  // ── I-02 Edit your pay ────────────────────────────────────────────────
  if (screen === 'edit') {
    const pay = editingPay;
    return layout('income', '1 of 2', (
      <PayForm key={pay?.id ?? pay?.payer ?? 'new'} pay={pay}
               onCancel={back}
               onSave={(fields) => (pay?.id ? editPay(pay.id, fields) : addPay(fields)).then((d) => {
                 setData(d);
                 // A corrected paycheque moves on to the bills; another
                 // source goes back to where she was.
                 if (pay && !pay.id) step('bills');
                 else back();
               })} />
    ), { onBack: back });
  }

  // ── I-03 No pay found ─────────────────────────────────────────────────
  if (screen === 'expected') {
    return layout('income', '1 of 2', (
      <ExpectedForm expected={data.expected}
                    onSave={(amount, varies) => saveExpected(amount, varies).then((d) => { setData(d); step('bills'); })}
                    // Remembered, so Home can make a rough estimate (H-03).
                    onSkip={() => skipExpected().then((d) => { setData(d); step('bills'); })
                      .catch(() => step('bills'))} />
    ), { onBack: back });
  }

  // ── I-05 Add or edit a bill ───────────────────────────────────────────
  if (screen === 'bill') {
    const bill = editingBill;
    return layout('bills', '2 of 2', (
      <BillForm key={bill?.key ?? 'new'} bill={bill} onCancel={back}
                onSave={(fields) => (bill ? editBill(bill.key, fields) : addBill(fields)).then((d) => {
                  setData(d);
                  if (bill) setTicked((t) => ({ ...t, [bill.key]: true }));
                  back();
                })}
                onRemove={() => removeBill(bill.key).then((d) => {
                  setData(d);
                  setTicked((t) => ({ ...t, [bill.key]: false }));
                  setRemoved(d.removed);
                  back();
                }).catch((e) => setError(e.message))} />
    ), { onBack: back });
  }

  // ── I-06 All set ──────────────────────────────────────────────────────
  if (screen === 'done') {
    return layout('done', ' ', (
      <>
        <img src={MARKS.closed} alt="" width="96" height="80" />
        <Heading title="That’s everything we need"
                 sub="Pearl can now work out what’s Allowance each month." />
        <div className="pk-tiles ib-tiles">
          <StatTile label="Income each month" value={tile(data.totals.income, 'Not set yet')} />
          <StatTile label="Regular bills" value={tile(data.totals.bills, 'None yet')} />
        </div>
        <div className="p-actions">
          <button type="button" className="p-btn primary" onClick={() => onDone?.(data)}>Continue</button>
        </div>
        <p className="p-note">You can change these any time in Profile › Income and bills.</p>
      </>
    ), { centered: true, onBack: null });
  }

  // ── I-04 Are these your regular bills? ────────────────────────────────
  return (
    <BillsScreen data={data} ticked={ticked ?? {}} busy={busy} error={error}
                 layout={layout}
                 onTick={(key, on) => setTicked((t) => ({ ...t, [key]: on }))}
                 onRent={(q) => run(async () => {
                   const d = await answerRent(q.key);
                   setTicked((t) => ({ ...t, [q.key]: true }));
                   return d;
                 })}
                 onEdit={(b) => { setEditingBill(b); step('bill'); }}
                 onAdd={() => { setEditingBill(null); step('bill'); }}
                 onConfirm={() => run(() => confirmBills(ticked), 'done')}
                 toast={removed && (
                   <ActionToast title={`${removed.name} removed`}
                                onUndo={() => {
                                  const r = removed;
                                  setRemoved(null);
                                  undoRemove(r).then((d) => {
                                    setData(d);
                                    setTicked((t) => ({ ...t, [r.key]: true }));
                                  }).catch((e) => setError(e.message));
                                }}
                                onDone={() => setRemoved(null)} />
                 )} />
  );
}

function BillsScreen({ data, ticked, busy, error, layout, onTick, onRent, onEdit, onAdd,
                       onConfirm, toast }) {
  const n = useMemo(() => data.bills.filter((b) => ticked[b.key]).length, [data, ticked]);
  const q = data.rent_question;
  return (
    <>
      {layout('bills', '2 of 2', (
        <>
          <Heading eyebrow="Your regular bills" title="Are these your regular bills?"
                   sub={data.bills.length ? 'Untick anything that isn’t a regular bill.'
                     : 'We didn’t find any regular bills yet. Add the ones you know about.'} />
          {q && (
            <Alert action="Yes, it’s my rent" onAction={() => onRent(q)}>{rentWords(q)}</Alert>
          )}
          {data.bills.length > 0 && (
            <div className="ib-list">
              {data.bills.map((b) => (
                <BillRow key={b.key} bill={b} ticked={!!ticked[b.key]}
                         onTick={(on) => onTick(b.key, on)} onEdit={() => onEdit(b)} />
              ))}
            </div>
          )}
          <button type="button" className="p-link ib-add" onClick={onAdd}>+ Add a bill we missed</button>
          {error && <Banner tone="caution">{error}</Banner>}
          <div className="p-actions ib-sticky">
            <button type="button" className="p-btn primary" disabled={busy} onClick={onConfirm}>
              {n === 0 ? 'Continue without bills' : `Confirm ${n} bill${n === 1 ? '' : 's'}`}
            </button>
          </div>
        </>
      ))}
      {toast}
    </>
  );
}
