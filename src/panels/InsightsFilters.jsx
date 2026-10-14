import { FilterChip } from '../pearl/kit.jsx';
import { LensToggle } from './Lens.jsx';

/**
 * The filters over Insights (2026-10-14): one account or all, how many
 * months, one-offs in or out, and one group or kind — plus the lens, by
 * need or by kind. Everything the page draws follows them.
 */
export function InsightsFilters({ d, lens, onLens, filters, onFilter }) {
  const accounts = [{ value: '', label: 'All accounts' },
                    ...(d.accounts ?? []).map((a) => ({ value: a.id, label: a.name }))];
  const spans = [{ value: '', label: 'Last 12 months' }, { value: '6', label: 'Last 6 months' },
                 { value: '3', label: 'Last 3 months' }];
  const shows = [{ value: '', label: 'All spending' },
                 { group: 'By need', options: [{ value: 'essentials', label: 'Essentials only' },
                                               { value: 'lifestyle', label: 'Lifestyle only' }] },
                 { group: 'By kind', options: [{ value: 'fixed', label: 'Fixed only' },
                                               { value: 'variable', label: 'Variable only' }] }];
  const oneOffs = [{ value: '', label: 'One-offs in' }, { value: 'out', label: 'One-offs left out' }];
  return (
    <div className="in-filters" aria-label="Filters">
      <LensToggle lens={lens} onChange={onLens} />
      <div className="in-filter-chips">
        <FilterChip label="Account" value={filters.account || ''} options={accounts}
                    active={!!filters.account} onChange={(v) => onFilter({ account: v })} />
        <FilterChip label="Months" value={filters.span || ''} options={spans}
                    active={!!filters.span} onChange={(v) => onFilter({ span: v })} />
        <FilterChip label="Show" value={filters.show || ''} options={shows}
                    active={!!filters.show} onChange={(v) => onFilter({ show: v })} />
        <FilterChip label="One-offs" value={filters.one_offs || ''} options={oneOffs}
                    active={!!filters.one_offs} onChange={(v) => onFilter({ one_offs: v })} />
      </div>
    </div>
  );
}
