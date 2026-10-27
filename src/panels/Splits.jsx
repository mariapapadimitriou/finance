import { useMemo, useState } from 'react';
import { Avatar, Choice, PButton, Segmented, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';

/**
 * Splits and repayments (Pearl S-01 to S-04, THL-124).
 *
 * Only her share counts anywhere, so a split is the one place the other
 * people's parts are named. Each of them is a repayment Pearl can watch for:
 * an e-Transfer from the same first name, for about what they owe, is offered
 * as that repayment (S-02). Repayments are never income.
 */

export const MAX_PEOPLE = 50;   // as finance/splits.py (2026-10-26: was 8)
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const shortDate = (iso) => {
  const [, m, d] = iso.split('-').map(Number);
  return `${MONTHS[m - 1]} ${d}`;
};

const cents = (x) => Math.round(Number(x) * 100);

/** The same rule as the server: even parts in cents, any odd cent stays with her. */
function evenParts(total, n) {
  const each = Math.floor(cents(total) / (n + 1));
  return Array.from({ length: n }, () => each / 100);
}

function names(people) {
  const named = people.map((p) => p.name.trim()).filter(Boolean);
  if (named.length === 0) return 'them';
  if (named.length === 1) return named[0];
  if (named.length === 2) return `${named[0]} and ${named[1]}`;
  return 'everyone';
}

/** "You": her own row, with a person icon rather than initials. */
function YouAvatar() {
  return <span className="pk-avatar sm" aria-hidden="true"><PIcon name="user" size={18} /></span>;
}

/**
 * Split this (S-01): evenly or by amount, with up to 50 people, and
 * "Watch for … paying me back".
 */
export function SplitThis({ tx, busy, onSave, onClear }) {
  const existing = tx.splitting;
  const total = tx.full_amount;
  const [mode, setMode] = useState(existing?.mode ?? 'even');
  const [people, setPeople] = useState(() => (existing?.people?.length
    ? existing.people.map((p) => ({ name: p.name, amount: String(p.amount) }))
    : [{ name: '', amount: '' }]));
  const [watch, setWatch] = useState(existing?.watch ?? true);

  const parts = useMemo(() => (mode === 'even'
    ? evenParts(total, people.length)
    : people.map((p) => (p.amount === '' ? 0 : Number(p.amount)))), [mode, total, people]);
  const theirs = parts.reduce((a, b) => a + cents(b), 0) / 100;
  const you = Math.round((total - theirs) * 100) / 100;
  const over = mode === 'amount' && you < -0.004;
  const negative = mode === 'amount' && parts.some((x) => !(x >= 0));
  const unnamed = people.some((p) => !p.name.trim());
  const ok = !over && !negative && !unnamed && people.length > 0;

  const set = (i, patch) => setPeople(people.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const remove = (i) => setPeople(people.filter((_, j) => j !== i));
  const add = () => setPeople([...people, { name: '', amount: '' }]);

  const save = () => onSave({
    mode, watch,
    people: people.map((p, i) => ({ name: p.name.trim(), amount: parts[i] })),
  });

  return (
    <div className="txd-step">
      <p className="pk-muted">Only your share counts toward your spending.</p>
      <Segmented label="Split how" value={mode} onChange={setMode}
                 options={[{ value: 'even', label: 'Evenly' }, { value: 'amount', label: 'By amount' }]} />
      <div className="sp-people" role="group" aria-label="People">
        <div className="sp-person">
          <YouAvatar />
          <span className="sp-name">You</span>
          <span className="sp-amt">{txAmount(Math.max(you, 0))}</span>
          <span className="sp-x" aria-hidden="true" />
        </div>
        {people.map((p, i) => (
          <div className="sp-person" key={i}>
            <Avatar name={p.name || '?'} />
            <input className="sp-name-input" type="text" value={p.name} maxLength={40}
                   placeholder="Name" aria-label={`Person ${i + 1} name`}
                   onChange={(e) => set(i, { name: e.target.value })} />
            {mode === 'even' ? (
              <span className="sp-amt">{txAmount(parts[i])}</span>
            ) : (
              <input className="sp-amt-input" type="number" inputMode="decimal" min="0" step="0.01"
                     value={p.amount} aria-label={`${p.name || `Person ${i + 1}`}’s part`}
                     aria-invalid={over ? 'true' : undefined}
                     onChange={(e) => set(i, { amount: e.target.value })} />
            )}
            <button type="button" className="sp-x" aria-label={`Remove ${p.name || 'this person'}`}
                    onClick={() => remove(i)} disabled={people.length === 1}>
              <PIcon name="x" size={16} />
            </button>
          </div>
        ))}
        {people.length < MAX_PEOPLE && (
          <button type="button" className="sp-add" onClick={add}>
            <PIcon name="users" size={18} /> Add someone
          </button>
        )}
      </div>
      {over && (
        <p className="txd-hint" role="alert">
          <PIcon name="alert" size={16} /> Their parts add up to more than {txAmount(total)}.
        </p>
      )}
      <Choice type="checkbox" checked={watch} onChange={setWatch}
              label={`Watch for ${names(people)} paying me back`}
              description={`When an e-Transfer from ${names(people)} arrives, we’ll ask if it’s for this. It won’t count as income.`} />
      <div className="sp-result">
        <div>
          <p className="pk-h3">Your share</p>
          <p className="pk-label">Counts toward {tx.category} · {txAmount(Math.max(theirs, 0))} less spending</p>
        </div>
        <span className="pk-h2">{txAmount(Math.max(you, 0))}</span>
      </div>
      <PButton className="txd-save" disabled={busy || !ok} onClick={save}>Save split</PButton>
      {existing && (
        <PButton variant="text" className="nl-skip" disabled={busy} onClick={onClear}>
          It was all mine
        </PButton>
      )}
    </div>
  );
}

/**
 * The split, once saved (S-04): her share, and for each person "Paid back
 * Oct 8" or "Owes $X". Edit goes back to Split this.
 */
export function SplitSummary({ tx, onEdit }) {
  const s = tx.splitting;
  return (
    <section className="sp-card" aria-label="Split">
      <div className="sp-card-head">
        <p className="pk-overline">{s.mode === 'even' ? 'Split evenly' : 'Split by amount'}</p>
        <button type="button" className="txd-link" onClick={onEdit}>Edit</button>
      </div>
      <div className="sp-person">
        <YouAvatar />
        <span className="sp-name">You</span>
        <span className="sp-amt">{txAmount(s.you)}</span>
      </div>
      {s.people.map((p) => (
        <div className="sp-person" key={p.name}>
          <Avatar name={p.name} />
          <span className="sp-name">{p.name}</span>
          {p.paid_on ? (
            <span className="sp-paid"><PIcon name="check" size={14} /> Paid back {shortDate(p.paid_on)}</span>
          ) : (
            <span className="pk-label pk-muted">
              {p.paid > 0 ? `Paid ${txAmount(p.paid)} · owes ${txAmount(p.owes)}` : `Owes ${txAmount(p.owes)}`}
            </span>
          )}
          <span className="sp-amt">{txAmount(p.amount)}</span>
        </div>
      ))}
    </section>
  );
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const longDate = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]}, ${LONG[m - 1]} ${d}`;
};

/** The split a repayment matches: what, when, and whose share (S-02). */
export function RepaymentMatch({ match }) {
  const partly = Math.abs(match.owes - match.share) >= 0.005;
  return (
    <div className="sp-match">
      <Avatar name={match.merchant} />
      <div className="sp-match-text">
        <span>{match.merchant} · split with {match.name}</span>
        <span className="pk-label pk-muted">
          {shortDate(match.date)} · {match.name}’s share {txAmount(match.share)}
          {partly ? ` · ${txAmount(match.owes)} still owed` : ''}
        </span>
      </div>
      {match.exact && (
        <span className="sp-paid"><PIcon name="check" size={14} /> Exact match</span>
      )}
    </div>
  );
}

/** "Is Priya paying you back for this?" with the split it matches (S-02). */
export function RepaymentQuestion({ match }) {
  return (
    <section className="sp-question" aria-label="Repayment">
      <p className="pk-h3">Is {match.name} paying you back for this?</p>
      <RepaymentMatch match={match} />
      <p className="pk-muted">If you link them, this e-Transfer won’t count as income, and the
        split shows as paid back.</p>
    </section>
  );
}

/**
 * Which split is this for? (S-03): the sender's open splits (or every open
 * one when Pearl can't tell who sent it), and None of these. A part
 * payment leaves the rest open.
 */
export function LinkToSplit({ tx, busy, onLink, onNone }) {
  const r = tx.repayment;
  const options = r?.splits ?? [];
  const first = options[0];
  const [pick, setPick] = useState(r?.suggestion
    ? `${r.suggestion.charge_id}|${r.suggestion.name}` : '');
  const sender = r?.from_sender && first ? first.name : null;
  // How much of it paid the split back: all of it to start (2026-10-26).
  const whole = tx.full_amount;
  const [part, setPart] = useState(() => Number(whole).toFixed(2));
  const n = Math.round(Number(part) * 100) / 100;
  const partOk = n > 0 && n <= whole + 0.005;
  const some = partOk && n < whole - 0.005 ? n : null;
  return (
    <div className="txd-step">
      <p className="pk-muted">
        {sender ? `Splits where ${sender} hasn’t paid you back yet.`
          : 'Splits still waiting to be paid back.'}
      </p>
      <div className="pk-choices" role="radiogroup" aria-label="Which split is this for?">
        {options.map((o) => {
          const key = `${o.charge_id}|${o.name}`;
          return (
            <Choice key={key} name="which-split" checked={pick === key} onChange={() => setPick(key)}
                    label={`${o.merchant} · ${txAmount(o.owes)}`}
                    description={`${longDate(o.date)} · ${o.name}’s share`} />
          );
        })}
        <Choice name="which-split" checked={pick === 'none'} onChange={() => setPick('none')}
                label="None of these"
                description="We’ll ask where it goes instead. It could be income or something else." />
      </div>
      {pick && pick !== 'none' && (
        <div className="txd-field">
          <label className="pk-label" htmlFor="paid-part">How much of it was paying you back?</label>
          <input id="paid-part" type="number" inputMode="decimal" min="0.01" step="0.01" max={whole}
                 value={part} disabled={busy} onChange={(e) => setPart(e.target.value)} />
          {some && <p className="pk-label pk-muted">{`The other ${txAmount(whole - some)} counts as money in`}</p>}
        </div>
      )}
      <p className="pk-impact"><PIcon name="info" size={18} />
        <span>Paid back part of their share? Pick the split and we’ll keep the rest open.</span></p>
      <PButton className="txd-save" disabled={busy || !pick || (pick !== 'none' && !partOk)}
               onClick={() => {
                 if (pick === 'none') { onNone(); return; }
                 const [chargeId, ...rest] = pick.split('|');
                 onLink(options.find((o) => o.charge_id === chargeId && o.name === rest.join('|')), some);
               }}>
        {pick === 'none' ? 'Choose a category' : 'Link'}
      </PButton>
    </div>
  );
}
