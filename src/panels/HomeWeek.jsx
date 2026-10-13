import { useState } from 'react';
import { checkAfford } from '../api.js';
import { DetailPanel, PButton, Segmented } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Field } from './GoalsParts.jsx';
import { heroCopy, longDate, monthName, parseAmount, shortDate, shown } from './HomePanel.jsx';

/**
 * The week under the month (THL-166 W-01 to W-03) and "Can I afford it?"
 * (THL-167 AF-01 to AF-03), as THL-185 draws them.
 *
 * The month stays the number; the week is one way of reading it. Its share
 * is re-split each Monday from what's safe to spend then, so what earlier
 * weeks didn't spend is already in it ("includes $45 from earlier weeks",
 * never a term in the sum: W1). Bills stay at month level (W3), and the
 * sheet shows the week and the rest of the month adding up to the month.
 *
 * "Can I afford it?" records nothing. It answers for the month with one line
 * on the week (A2); when it doesn't fit it says by how much, and whether a
 * usual next month would cover it (A1). Never "no", never red.
 */

const DAYS_OF = (n) => `${n} ${n === 1 ? 'day' : 'days'}`;

/** "Oct 5–11", or "Oct 31" for a one-day week. */
export function weekRange(w) {
  if (w.start === w.end) return shortDate(w.start);
  return `${shortDate(w.start)}–${Number(w.end.slice(8, 10))}`;
}

/** Earlier weeks' leftover, in words, when there's a dollar of it. */
const fromEarlier = (w) => (w.rolled_over >= 1 ? `includes ${shown(w.rolled_over)} from earlier weeks` : null);

/** The safe-to-spend card's words with the week as the main view (W-02). */
export function weekHeroCopy(w, s) {
  const range = weekRange(w);
  const month = monthName(s.month);
  const label = 'Safe to spend this week';
  if (w.state === 'over') {
    return {
      label, figure: shown(w.over_by, true), figureWords: 'past this week’s plan', pill: null,
      context: s.state === 'over'
        ? [range, s.next_pay ? `Your next pay arrives on ${longDate(s.next_pay)}.` : null].filter(Boolean).join(' · ')
        : w.rest_days > 0 ? `${range} · it comes out of the rest of ${month}` : range,
    };
  }
  if (w.estimate) {
    return {
      label, pill: w.estimate === 'rough' ? 'Estimate' : 'Cautious',
      figure: w.shown >= 10 ? `${w.estimate === 'rough' ? 'About ' : ''}${shown(w.shown)}` : 'Less than $10',
      context: [range, w.estimate === 'rough' ? 'rough estimate' : 'cautious estimate'].join(' · '),
    };
  }
  if (w.left === 0) {
    return { label, figure: null, pill: null, context: `${range} · this week’s share is used up exactly` };
  }
  return {
    label, figure: shown(w.left, true), pill: 'On track',
    context: [range, w.per_day >= 1 ? `about ${shown(w.per_day)} a day` : null, fromEarlier(w)]
      .filter(Boolean).join(' · '),
  };
}

/** The week strip's words (W-01), whole dollars. */
export function weekLine(w) {
  if (w.state === 'over') return `${shown(w.over_by)} past this week’s plan`;
  if (w.left === 0) return 'This week’s share is used up';
  const left = w.estimate ? (w.shown >= 10 ? `About ${shown(w.shown)}` : 'Less than $10') : shown(w.left);
  return [`${left} left`, w.per_day >= 1 ? `about ${shown(w.per_day)} a day` : null,
          w.rolled_over >= 1 ? `${shown(w.rolled_over)} rolled over` : null]
    .filter(Boolean).join(' · ');
}

/** The month strip's words when the week is the main view (W-02). */
export function monthLine(s) {
  if (s.state === 'over') return `${shown(s.over_by, true)} past this month’s plan`;
  const c = heroCopy(s);
  if (!c.figure) return 'This month’s plan is used up';
  return `${c.figure} left · ${DAYS_OF(s.days_left)}`;
}

/** Month / Week (W-02). Her choice is saved on her account. */
export function ViewToggle({ view, onView }) {
  return (
    <div className="hm-toggle">
      <Segmented label="Show safe to spend for" value={view} onChange={onView}
                 options={[{ value: 'month', label: 'This month' }, { value: 'week', label: 'This week' }]} />
    </div>
  );
}

/** The strip under the card (W-01, W-02): the other view, in one line. */
export function WeekStrip({ view, s, w, onView }) {
  const week = view === 'month';
  return (
    <section className="hm-strip" aria-label={week ? 'This week' : 'This month'}>
      <span className="hm-strip-label">{week ? 'This week' : 'This month'}</span>
      <span className="hm-strip-text">{week ? weekLine(w) : monthLine(s)}</span>
      <button type="button" className="hm-link hm-strip-link" onClick={() => onView(week ? 'week' : 'month')}>
        {week ? 'See week' : 'See month'} <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** The sheet's rows for the week (W-03), and the week and the rest of the
 * month adding up to the month. No signs; the labels carry the direction. */
export function weekSheetRows(w, s) {
  const month = monthName(s.month);
  const daysThen = w.days + w.rest_days;
  const shareDetail = [
    `${shown(w.at_start, true)} safe to spend when the week began, split by days: ${w.days} of the ${daysThen} days left`,
    w.rolled_over >= 1 ? `Includes ${shown(w.rolled_over, true)} from earlier weeks` : null,
    w.rolled_over <= -1 ? `${shown(w.rolled_over, true)} less, because earlier weeks went over` : null,
  ].filter(Boolean).join('. ');
  const rows = [
    { key: 'share', label: `This week’s share of ${month}`, detail: shareDetail,
      display: w.share > 0 ? shown(w.share, true) : 'Nothing' },
    { key: 'spent', label: 'Spent so far this week',
      detail: 'Bills aren’t counted here; the month already sets them aside',
      display: w.spent > 0 ? shown(w.spent, true) : 'Nothing yet' },
  ];
  const total = w.state === 'over'
    ? { label: 'Past this week’s plan', display: shown(w.over_by, true),
        detail: w.rest_days > 0 ? `It comes out of the rest of ${month}` : null }
    : { label: 'Left this week', display: w.left > 0 ? shown(w.left, true) : 'Nothing left',
        detail: w.per_day >= 1 ? `About ${shown(w.per_day)} a day for ${DAYS_OF(w.days_left)}` : null };
  const adds = [
    w.state === 'over'
      ? { label: 'This week, past its plan', display: shown(w.over_by, true) }
      : { label: 'Left this week', display: shown(w.left, true) },
  ];
  if (w.rest_days > 0) {
    adds.push(w.rest_of_month >= 0
      ? { label: `The rest of ${month} (${DAYS_OF(w.rest_days)})`, display: shown(w.rest_of_month, true) }
      : { label: `The rest of ${month}, past its plan`, display: shown(w.rest_of_month, true) });
  }
  const sum = s.state === 'over'
    ? { label: 'Past this month’s plan', display: shown(s.over_by, true) }
    : { label: `Safe to spend in ${month}`, display: shown(s.amount, true) };
  const note = w.estimate && w.state !== 'over' && w.left > 0
    ? (w.shown >= 10 ? `Shown rounded down to ${shown(w.shown)}.` : 'Shown as less than $10.')
    : null;
  return { rows, total, adds, sum, note };
}

/** "How we worked this out" for the week (W-03). */
export function WeekSheet({ w, s, onClose }) {
  const { rows, total, adds, sum, note } = weekSheetRows(w, s);
  const month = monthName(s.month);
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} sheet className="hm-sheet">
      <h1 className="pk-h2">{`This week, ${weekRange(w)}`}</h1>
      <div className="hm-ledger">
        {rows.map((r) => (
          <div key={r.key} className="hm-row hm-row-static">
            <span className="hm-row-text">
              <span className="hm-row-label">{r.label}</span>
              <span className="hm-row-detail">{r.detail}</span>
            </span>
            <span className="hm-row-amount">{r.display}</span>
          </div>
        ))}
        <div className="hm-total">
          <span className="hm-row-text">
            <span className="pk-h3">{total.label}</span>
            {total.detail && <span className="hm-row-detail">{total.detail}</span>}
          </span>
          <span className="pk-h3">{total.display}</span>
        </div>
      </div>
      {note && <p className="pk-muted hm-note">{note}</p>}
      <h2 className="pk-h3">{`How the weeks add up to ${month}`}</h2>
      <dl className="hm-facts hm-adds">
        {adds.map((a) => (
          <div key={a.label}><dt>{a.label}</dt><dd>{a.display}</dd></div>
        ))}
        <div className="hm-adds-total"><dt>{sum.label}</dt><dd>{sum.display}</dd></div>
      </dl>
      <p className="pk-muted hm-note">
        {`Your share is what’s safe to spend in ${month} split across the days left, so the weeks always add up to the month. It’s worked out again each Monday.`}
      </p>
      <div className="hm-sheet-foot">
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** What "Can I afford it?" says (AF-02, AF-03). Whole dollars, except the
 * "from" figure, which matches the card in cents. */
export function affordCopy(r, s) {
  const month = monthName(s.month);
  const amt = shown(r.amount);
  if (r.fits) {
    const before = r.estimate ? `about ${shown(r.before)}` : shown(r.before, true);
    const perDay = r.per_day_after >= 1
      ? `, about ${shown(r.per_day_after)} a day for the ${DAYS_OF(r.days_left)} left` : '';
    let week = null;
    if (r.week?.within) {
      week = r.week.left_after > 0 ? `This week you’d still have ${shown(r.week.left_after)}.`
        : 'It would use up this week’s share exactly.';
    } else if (r.week?.left > 0) {
      week = `That’s more than this week’s ${shown(r.week.left)}, so the weeks after would have a little less.`;
    } else if (r.week) {
      week = `This week’s share is already used, so it would come from the rest of ${month}.`;
    }
    return {
      title: `Yes, ${amt} fits this month.`,
      lines: [`Safe to spend goes from ${before} to ${shown(r.after)}${perDay}.`, week].filter(Boolean),
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
