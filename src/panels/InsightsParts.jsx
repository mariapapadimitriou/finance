import { GROUPS, PANELS } from '../nav.js';
import PIcon from '../pearl/icons.jsx';
import { monthFull } from './insightsMath.js';

// Small parts shared by Growth › Insights and its detail views (THL-196
// GR-28 to GR-32, THL-186 GR-25 to GR-27): the Growth pills, the month
// switcher, the "See more  ›" link and a category's dot.

/** The Growth pills (GR-01's tabs): Path, Insights, Projections, Budgets, Debts, and Learn to come. */
export function GrowthTabs({ current = 'insights', onTab }) {
  const growth = GROUPS.find((g) => g.key === 'growth');
  return (
    <nav className="in-tabs" aria-label="Growth">
      {growth.panels.map((key) => (
        <button key={key} type="button" className="in-tab" aria-current={key === current ? 'page' : undefined}
                onClick={() => onTab?.(key)}>
          {PANELS[key].label}
        </button>
      ))}
      <button type="button" className="in-tab" disabled aria-describedby="in-learn-soon">
        Learn
      </button>
      <span id="in-learn-soon" className="pk-sr">Coming later</span>
    </nav>
  );
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

