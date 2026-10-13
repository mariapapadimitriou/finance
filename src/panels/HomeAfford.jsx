import { useState } from 'react';
import { checkAfford } from '../api.js';
import { PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Field } from './GoalsParts.jsx';
import { monthName, parseAmount, shown } from './HomePanel.jsx';

/**
 * "Can I afford it?" on Home (THL-167 AF-01 to AF-03), as THL-185 draws it.
 *
 * It records nothing. It answers for the month: when it fits, what safe to
 * spend would be after it; when it doesn't, by how much, and whether a usual
 * next month would cover it (A1). Never "no", never red. Home reads by the
 * month only, so the answer says nothing about weeks.
 */

const DAYS_OF = (n) => `${n} ${n === 1 ? 'day' : 'days'}`;

/** What "Can I afford it?" says (AF-02, AF-03). Whole dollars, except the
 * "from" figure, which matches the card in cents. */
export function affordCopy(r, s) {
  const month = monthName(s.month);
  const amt = shown(r.amount);
  if (r.fits) {
    const before = r.estimate ? `about ${shown(r.before)}` : shown(r.before, true);
    const perDay = r.per_day_after >= 1
      ? `, about ${shown(r.per_day_after)} a day for the ${DAYS_OF(r.days_left)} left` : '';
    return {
      title: `Yes, ${amt} fits this month.`,
      lines: [`Safe to spend goes from ${before} to ${shown(r.after)}${perDay}.`],
      chest: false,
    };
  }
  const n = r.next_month;
  const next = n ? monthName(n.month) : 'next month';
  const short = r.already_over
    ? `${month}’s plan is already used up, so ${amt} would come from ${next}.`
    : `${amt} is ${shown(r.short_by)} more than what’s left in ${month}.`;
  if (n?.fits) {
    const leaving = n.per_day_after >= 1 ? `, leaving about ${shown(n.per_day_after)} a day` : '';
    return {
      title: 'Not this month, but soon.',
      lines: [`${short} If ${next} looks like a usual month, it would fit then${leaving}.`],
      chest: true,
    };
  }
  return {
    title: 'This one needs saving up for.',
    lines: [`${short} It’s also more than a usual month leaves after bills, so a treasure chest can spread it over a few months.`],
    chest: true,
  };
}

/** "Can I afford it?" (AF-01). Checking records nothing. */
export function AffordCard({ s, onChest, check = checkAfford }) {
  const [value, setValue] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const amount = parseAmount(value);
    if (!(amount > 0)) { setError('Enter what it costs, like 180.'); setResult(null); return; }
    setError(null);
    setBusy(true);
    check(amount).then(setResult).catch((err) => setError(err.message)).finally(() => setBusy(false));
  };
  const copy = result && affordCopy(result, s);
  return (
    <form className="hm-card hm-afford" onSubmit={submit} aria-labelledby="hm-afford-title">
      <h2 className="pk-h3" id="hm-afford-title">Can I afford it?</h2>
      <div className="hm-afford-row">
        <Field label="It costs" id="hm-afford-amount" error={error}>
          <input id="hm-afford-amount" inputMode="decimal" autoComplete="off" placeholder="$180"
                 value={value} onChange={(e) => { setValue(e.target.value); setResult(null); }} />
        </Field>
        <PButton type="submit" variant="secondary" disabled={busy}>{busy ? 'Checking…' : 'Check'}</PButton>
      </div>
      <div role="status" aria-live="polite" className="hm-afford-live">
        {copy && (
          <div className="hm-afford-result">
            <p className="hm-row-label">{copy.title}</p>
            {copy.lines.map((l) => <p key={l}>{l}</p>)}
            {copy.chest && (
              <button type="button" className="hm-link" onClick={onChest}>
                Set it aside in a treasure chest <PIcon name="chevronRight" size={14} />
              </button>
            )}
          </div>
        )}
      </div>
    </form>
  );
}
