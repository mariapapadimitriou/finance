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

/** On a phone (2026-10-23): the month as three numbers, no chart. */
export function monthStats(spent = 0, income = 0) {
  const s = Math.max(0, spent);
  const i = Math.max(0, income);
  const left = i - s;
  return [
    { key: 'spent', label: 'Spent', value: txAmount(s), tone: 'out' },
    { key: 'in', label: 'Came in', value: txAmount(i), tone: 'in' },
    left < -EPS
      ? { key: 'left', label: 'Over', value: txAmount(-left), tone: 'over' }
      : { key: 'left', label: 'Left', value: txAmount(left), tone: 'left' },
  ];
}

// Spent and Came in filter the list below (2026-10-26); Left doesn't.
const SHOWS = { spent: 'spending', in: 'income' };
const SHOWING = { spending: 'Showing what you spent', income: 'Showing what came in' };

function Stats({ spent, income, ghost = false, counts = '', onCounts }) {
  return (
    <div className="tm-stats" aria-hidden={ghost ? 'true' : undefined}>
      {monthStats(spent, income).map((s) => {
        const inner = (
          <>
            <span className="tm-stat-label">{s.label}</span>
            {ghost ? <span className="tm-stat-value tm-ghost-text" /> : <span className="tm-stat-value">{s.value}</span>}
          </>
        );
        const shows = SHOWS[s.key];
        if (ghost || !shows || !onCounts) return <div key={s.key} className={`tm-stat ${s.tone}`}>{inner}</div>;
        return (
          <button key={s.key} type="button" className={`tm-stat ${s.tone}${counts === shows ? ' on' : ''}`}
                  aria-pressed={counts === shows} onClick={() => onCounts(shows)}>
            {inner}
          </button>
        );
      })}
    </div>
  );
}

/** A bar row that filters the list when tapped (desktop). */
function Row({ shows, counts, onCounts, children }) {
  if (!onCounts) return <div className="tm-row" aria-hidden="true">{children}</div>;
  return (
    <button type="button" className={`tm-row tm-pick${counts === shows ? ' on' : ''}`}
            aria-pressed={counts === shows} aria-label={SHOWING[shows]} onClick={() => onCounts(shows)}>
      {children}
    </button>
  );
}

export default function FlowCards({ totals, counts = '', onCounts }) {
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
        <Stats spent={0} income={0} ghost />
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
      <Row shows="income" counts={counts} onCounts={onCounts}>
        <span className="tm-label">My income</span>
        <span className="tm-track">
          <span className="tm-bar in" style={{ width: pct(m.income) }} />
          {m.over > EPS && <span className="tm-income-line" style={{ left: pct(m.income) }} />}
        </span>
        <span className="tm-amt in">{txAmount(income, { inflow: income > EPS })}</span>
      </Row>
      <Row shows="spending" counts={counts} onCounts={onCounts}>
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
      </Row>
      {leftWords(spent, income) && <p className="tm-left" aria-hidden="true">{leftWords(spent, income)}</p>}
      <Stats spent={spent} income={income} counts={counts} onCounts={onCounts} />
      {SHOWING[counts] && onCounts && (
        <p className="tm-showing">
          {SHOWING[counts]}
          <button type="button" className="txd-link" onClick={() => onCounts(counts)}>Show all</button>
        </p>
      )}
    </section>
  );
}
