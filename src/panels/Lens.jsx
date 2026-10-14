import { Segmented } from '../pearl/kit.jsx';

/**
 * Two lenses on spending (2026-10-14; finance/kinds.py): by need —
 * Essentials and Lifestyle, what it was for — and by kind — Fixed and
 * Variable, whether it was going to happen anyway. Insights, Home's
 * snapshot, Budgets and the Transactions filter all offer both; the choice
 * is remembered on this device.
 */

export const LENSES = {
  need: { keys: ['essentials', 'lifestyle'], labels: { essentials: 'Essentials', lifestyle: 'Lifestyle' },
          caption: 'Essentials and Lifestyle' },
  kind: { keys: ['fixed', 'variable'], labels: { fixed: 'Fixed', variable: 'Variable' },
          caption: 'Fixed and Variable' },
};
const KEY = 'pearl-lens';

export function readLens() {
  try { return localStorage.getItem(KEY) === 'kind' ? 'kind' : 'need'; } catch { return 'need'; }
}
export function writeLens(lens) {
  try { localStorage.setItem(KEY, lens); } catch { /* this view only */ }
}

/** The two-way switch. */
export function LensToggle({ lens, onChange, label = 'See spending' }) {
  return (
    <Segmented label={label} value={lens} onChange={onChange}
               options={[{ value: 'need', label: 'By need' }, { value: 'kind', label: 'By kind' }]} />
  );
}

/** A trend month with the chosen lens's two parts in the chart's slots. */
export function trendForLens(months, lens) {
  if (lens !== 'kind') return months;
  return months.map((m) => ({ ...m, essentials: m.fixed ?? 0, lifestyle: m.variable ?? 0 }));
}

/** A where-it-went month with the chosen lens's groups. */
export function whereForLens(where, lens) {
  if (lens !== 'kind' || !where?.kinds) return where;
  return { ...where, groups: where.kinds };
}

export const lensLegend = (lens) => LENSES[lens].keys.map((k) => ({
  label: LENSES[lens].labels[k], tone: `in-${k}` }));
