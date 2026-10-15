import { GROUPS, PANELS } from '../nav.js';
import PIcon from '../pearl/icons.jsx';
import { monthFull } from './insightsMath.js';

// Small parts shared by Cash flow › Insights and its detail views (THL-196
// GR-28 to GR-32, THL-186 GR-25 to GR-27): a group's pills, the month
// switcher, the "See more  ›" link and a category's dot.

// Pages that aren't a tab of their group: Needs a look is reached from the
// list's alert and has its own way back.
const NOT_A_TAB = new Set(['review']);

/** A group's pages as pills (2026-10-15): Cash flow's Transactions ·
 * Insights · Budgets · Debts. A group with one page, or one whose pages are
 * reached from the page itself (Save, THL-248), draws nothing. */
export function GroupTabs({ group, current, onTab }) {
  const g = GROUPS.find((x) => x.key === group);
  const panels = (g?.panels ?? []).filter((k) => !NOT_A_TAB.has(k));
  if (panels.length < 2 || g?.tabs === false) return null;
  return (
    <nav className="in-tabs" aria-label={g.label}>
      {panels.map((key) => (
        <button key={key} type="button" className="in-tab" aria-current={key === current ? 'page' : undefined}
                onClick={() => onTab?.(key)}>
          {PANELS[key].label}
        </button>
      ))}
    </nav>
  );
}

/** Cash flow's tabs: Transactions · Insights. */
export function CashFlowTabs({ current = 'transactions', onTab }) {
  return <GroupTabs group="cashflow" current={current} onTab={onTab} />;
}

/** The pills of whichever group `current` is in (the old Growth pills). */
export function GrowthTabs({ current = 'insights', onTab }) {
  const g = GROUPS.find((x) => x.panels.includes(current));
  return g ? <GroupTabs group={g.key} current={current} onTab={onTab} /> : null;
}

/** "‹ October so far ›": the month, and the ones either side of it. */
export function MonthSwitcher({ label, prev, next, onPrev, onNext, small = false }) {
  return (
    <div className={`in-switch${small ? ' small' : ''}`}>
      <button type="button" className="in-switch-btn" onClick={onPrev} disabled={!prev}
              aria-label={prev ? `Review ${monthFull(prev)}` : 'No earlier month'}>
        <PIcon name="chevronRight" size={14} className="in-flip" />
      </button>
      <h2 className={small ? 'pk-h3' : 'pk-h2'} aria-live="polite">{label}</h2>
      <button type="button" className="in-switch-btn" onClick={onNext} disabled={!next}
              aria-label={next ? (next.current ? 'Back to this month' : `Review ${monthFull(next.month)}`)
                : 'No later month'}>
        <PIcon name="chevronRight" size={14} />
      </button>
    </div>
  );
}

/** "See the trend  ›". */
export function More({ children, onClick, label }) {
  return (
    <button type="button" className="in-more" onClick={onClick} aria-label={label}>
      {children}<span aria-hidden="true">  ›</span>
    </button>
  );
}

/** A category's dot: Essentials or Lifestyle; dashed while Pearl isn't sure (AI). */
export function CatDot({ group, unsure = false }) {
  if (unsure) {
    return (
      <span className="in-cat-dot in-guess" title="Suggested by Pearl">
        <span className="pk-sr">Category suggested by Pearl, needs a look:</span>
      </span>
    );
  }
  return <span className={`in-cat-dot ${group === 'essentials' ? 'in-essentials' : 'in-lifestyle'}`} aria-hidden="true" />;
}

