import { txAmount } from '../pearl/kit.jsx';
import './flowcards.css';

/**
 * This month (Current design, 2026-10-20): one card over the list with two
 * rounded bars from the same left edge, on one scale — "My income" in
 * lagoon and "What I spent" in rose — with the amounts on the right and
 * nothing else. When spending runs past income, the part of the spending
 * bar beyond the income line is drawn hollow and dashed, labelled "$x
 * over", and a dashed line drops from the end of the income bar across
 * both rows so the eye can compare them. Only counted flows: spending (her
 * share, less what a chest paid) and income; transfers, card payments and
 * savings are in neither.
 *
 * The Outflows and Inflows line cards it replaces (ALT-04, 2026-10-17)
 * asked the reader to add two sides in their head; two bars from one origin
 * answer "is more coming in than going out, and by how much?" at a glance.
 */

const EPS = 0.005;

/** The two bars as fractions of the longer one, and the overshoot. */
export function barMath(spent = 0, income = 0) {
  const s = Math.max(0, spent);
  const i = Math.max(0, income);
  const top = Math.max(s, i);
  const frac = (v) => (top > EPS ? v / top : 0);
  return {
    income: frac(i),
    spent: frac(s),
    over: s > i + EPS ? s - i : 0,
    overFrac: s > i + EPS ? frac(s - i) : 0,
  };
}

/** Words for a screen reader: the two figures and how they compare. */
export function cardWords(totals) {
  if (!totals) return '';
  const spent = Math.max(0, totals.spent ?? 0);
  const income = Math.max(0, totals.income ?? 0);
  const base = `Income ${txAmount(income)}, spent ${txAmount(spent)}.`;
  if (spent > income + EPS) return `${base} ${txAmount(spent - income)} more out than in.`;
  if (income > spent + EPS) return `${base} ${txAmount(income - spent)} more in than out.`;
  return base;
}

/** One quiet line under the bars (2026-10-21): "$3,121.24 left this month",
 * or how far spending has run past income. Nothing when they're even. */
export function leftWords(spent = 0, income = 0) {
  const s = Math.max(0, spent);
  const i = Math.max(0, income);
  if (i > s + EPS) return `${txAmount(i - s)} left this month`;
  if (s > i + EPS) return `${txAmount(s - i)} more out than in this month`;
  return '';
}

export default function FlowCards({ totals }) {
  // Not loaded yet: the same card at the same height, so nothing below it
  // jumps when the numbers arrive (2026-10-21).
  if (!totals) {
    return (
      <section className="tm-card tm-skeleton" aria-label="This month" aria-busy="true">
        {['My income', 'What I spent'].map((label) => (
          <div className="tm-row" key={label} aria-hidden="true">
            <span className="tm-label">{label}</span>
            <span className="tm-track"><span className="tm-bar tm-ghost" /></span>
            <span className="tm-amt tm-ghost-text" />
          </div>
        ))}
      </section>
    );
  }
  const spent = Math.max(0, totals.spent ?? 0);
  const income = Math.max(0, totals.income ?? 0);
  const m = barMath(spent, income);
  const pct = (f) => `${(f * 100).toFixed(2)}%`;
  return (
    <section className="tm-card" aria-label="This month">
      <p className="pk-sr">{cardWords(totals)}</p>
      <div className="tm-row" aria-hidden="true">
        <span className="tm-label">My income</span>
        <span className="tm-track">
          <span className="tm-bar in" style={{ width: pct(m.income) }} />
          {m.over > EPS && <span className="tm-income-line" style={{ left: pct(m.income) }} />}
        </span>
        <span className="tm-amt in">{txAmount(income, { inflow: income > EPS })}</span>
      </div>
      <div className="tm-row" aria-hidden="true">
        <span className="tm-label">What I spent</span>
        <span className="tm-track">
          <span className="tm-bar out" style={{ width: pct(m.over > EPS ? m.income : m.spent) }} />
          {m.over > EPS && (
            <span className="tm-over" style={{ left: pct(m.income), width: pct(m.overFrac) }}>
              <span className="tm-over-label">{`${txAmount(m.over)} over`}</span>
            </span>
          )}
        </span>
        <span className="tm-amt out">{txAmount(spent, { signed: spent > EPS })}</span>
      </div>
      {leftWords(spent, income) && <p className="tm-left" aria-hidden="true">{leftWords(spent, income)}</p>}
    </section>
  );
}
