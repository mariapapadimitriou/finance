import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, CategoryChip, DayHeader, EmptyState, FilterChip, PButton, SearchField, StatTile, TxRow,
  txAmount,
} from '../pearl/kit.jsx';
import { ErrorNote } from '../components/ui.jsx';
import { accountTitle, getTxList } from '../api.js';
import { readTxUrl, writeTxUrl } from '../router.js';

/**
 * Transactions (Pearl TX-01 to TX-03, THL-122).
 *
 * Opens on this calendar month, every account and every category, newest
 * first, grouped by day. Search and the three filters combine, and live in
 * the address bar so a filtered list can be linked to and survives back and
 * forward. What each row says — its amount, whether it counts, its chip and
 * its note — comes from the server, so the list and the month never disagree.
 *
 * Opened on a group or a category (TX-02, e.g. from Home's "See where it
 * went"), the title names it and the tiles compare it with a usual month.
 * With nothing to show (TX-03) the filters stay in view so she can see why,
 * and nothing is drawn in an error colour.
 */

const PAGE = 25;
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const thisMonth = () => isoDay(new Date()).slice(0, 7);

function monthName(month, withYear = false) {
  const [y, m] = month.split('-').map(Number);
  const name = MONTHS[m - 1] ?? month;
  return withYear || y !== new Date().getFullYear() ? `${name} ${y}` : name;
}

/** "Today · Friday, October 9", "Yesterday · …", or "Thursday, October 8". */
function dayLabel(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const label = `${WEEKDAYS[date.getDay()]}, ${MONTHS[m - 1]} ${d}`
    + (y !== new Date().getFullYear() ? `, ${y}` : '');
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (iso === isoDay(today)) return `Today · ${label}`;
  if (iso === isoDay(yesterday)) return `Yesterday · ${label}`;
  return label;
}

/** The filters, from the address bar, with the defaults filled in. */
function fromUrl() {
  const url = readTxUrl();
  const f = url?.filters ?? {};
  return { month: f.month || thisMonth(), account: f.account || '', group: f.group || '',
           category: f.category || '', q: f.q || '', from: url?.from || '' };
}

const DEFAULTS = () => ({ month: thisMonth(), account: '', group: '', category: '', from: '' });

export default function TransactionsList({ summary, categories, accounts, reviewCount = 0,
                                           onTab, version }) {
  const [filters, setFilters] = useState(fromUrl);
  const [query, setQuery] = useState(filters.q);
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const request = useRef(0);

  // The address bar follows the filters. Defaults stay out of it, so the
  // plain list is just /transactions.
  const urlFilters = (f) => ({ ...f, month: f.month === thisMonth() ? '' : f.month });
  const toUrl = (f, push = false) => writeTxUrl({ filters: urlFilters(f), from: f.from }, { push });
  useEffect(() => { toUrl(filters); }, [filters]);

  // Back and forward move between filter states.
  useEffect(() => {
    const onPop = () => {
      if (!readTxUrl()) return;
      const next = fromUrl();
      setFilters(next);
      setQuery(next.q);
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // Search waits for a pause in typing, and doesn't add a history entry per key.
  useEffect(() => {
    if (query === filters.q) return undefined;
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: query })), 250);
    return () => clearTimeout(t);
  }, [query, filters.q]);

  const choose = (patch) => {
    const next = { ...filters, ...patch };
    toUrl(next, true);
    setFilters(next);
  };
  const filtered = filters.month !== thisMonth() || !!filters.account
    || !!filters.group || !!filters.category;
  // Back to TX-01's defaults; the search, if any, is its own control.
  const clearFilters = () => choose(DEFAULTS());
  const clearSearch = () => { setQuery(''); choose({ q: '' }); };

  const fetchPage = useCallback(async (offset) => {
    const id = ++request.current;
    try {
      const { from, ...params } = filters;
      const res = await getTxList({ ...params, limit: PAGE, offset });
      if (id !== request.current) return;
      setError(null);
      setData(res);
      setRows((prev) => (offset ? [...prev, ...res.transactions] : res.transactions));
    } catch (e) {
      if (id === request.current) setError(e);
    }
  }, [filters]);

  // A new filter starts from the first page; the old rows stay until the new
  // ones arrive, so the list doesn't flash empty.
  useEffect(() => { fetchPage(0); }, [fetchPage, version]);

  const showMore = async () => {
    setLoadingMore(true);
    await fetchPage(rows.length);
    setLoadingMore(false);
  };

  // ── Filter options ────────────────────────────────────────────────────
  const monthOptions = useMemo(() => {
    const months = new Set([thisMonth(), ...(summary?.months ?? [])]);
    if (filters.month) months.add(filters.month);
    return [...months].sort().reverse().map((m) => ({ value: m, label: monthName(m) }));
  }, [summary, filters.month]);

  const accountOptions = useMemo(() => [
    { value: '', label: 'All accounts' },
    ...accounts.map((a) => ({ value: a.account_id, label: accountTitle(a) })),
  ], [accounts]);

  const groups = data?.groups ?? { essentials: 'Essentials', lifestyle: 'Lifestyle',
    income: 'Income', savings: 'Savings', transfer: 'Transfer' };
  const categoryOptions = useMemo(() => [
    { value: '', label: 'All categories' },
    { group: 'Groups', options: Object.entries(groups).map(([k, v]) => ({ value: `g:${k}`, label: v })) },
    { group: 'Categories', options: categories.map((c) => ({ value: `c:${c.name}`, label: c.name })) },
  ], [categories, groups]);
  const categoryValue = filters.group ? `g:${filters.group}`
    : filters.category ? `c:${filters.category}` : '';
  const categoryLabel = filters.group ? groups[filters.group]
    : filters.category || 'All categories';
  const pickCategory = (v) => choose({
    group: v.startsWith('g:') ? v.slice(2) : '',
    category: v.startsWith('c:') ? v.slice(2) : '',
  });

  // ── Rows by day ───────────────────────────────────────────────────────
  const days = useMemo(() => {
    const out = [];
    rows.forEach((r) => {
      const last = out[out.length - 1];
      if (last && last.date === r.date) last.rows.push(r);
      else out.push({ date: r.date, rows: [r] });
    });
    return out;
  }, [rows]);

  const totals = data?.totals;
  const focus = data?.focus;           // set when a group or category is chosen
  const more = (data?.total ?? 0) - rows.length;
  const empty = !!data && rows.length === 0;
  const anySuggested = rows.some((r) => r.suggested);
  const open = (id) => writeTxUrl({ id, filters: urlFilters(filters), from: filters.from },
                                  { push: true });

  // The title says what the list is: "Lifestyle in October" when it is one
  // group or category, otherwise just Transactions.
  const focusLabel = filters.group ? groups[filters.group] : filters.category;
  const title = focusLabel ? `${focusLabel} in ${monthName(filters.month)}` : 'Transactions';
  const overline = filters.from === 'home' ? 'From Home' : monthName(filters.month, true);

  return (
    <div className="pk tx-page">
      <header className="tx-head">
        <p className="pk-overline accent">{overline}</p>
        <h1 className="pk-h1">{title}</h1>
      </header>

      <div className="tx-toolbar">
        <SearchField value={query} onChange={setQuery} label="Search transactions"
                     placeholder="Search merchants or amounts" />
        <div className="tx-chips">
          <FilterChip label="Month" value={filters.month} options={monthOptions}
                      active={filters.month !== thisMonth()}
                      onChange={(v) => choose({ month: v })} />
          <FilterChip label="Account" value={filters.account} options={accountOptions}
                      active={!!filters.account} onChange={(v) => choose({ account: v })} />
          <FilterChip label="Category" value={categoryValue} options={categoryOptions}
                      shown={categoryLabel} active={!!categoryValue} onChange={pickCategory} />
          {filtered && !empty && (
            <PButton variant="text" className="tx-clear" onClick={clearFilters}>
              Clear filters
            </PButton>
          )}
        </div>
      </div>

      {error && <ErrorNote error={error} onRetry={() => fetchPage(0)} />}

      {empty ? (
        <Empty filters={filters} q={filters.q} filtered={filtered}
               onClearSearch={clearSearch} onClearFilters={clearFilters} />
      ) : (
        <>
          {totals && (focus ? (
            <div className="pk-tiles">
              <StatTile label={`${focus.label} so far`} value={txAmount(focus.total)} />
              <StatTile label="In a usual month"
                        value={focus.usual == null ? '—' : txAmount(focus.usual)} />
              <StatTile label="Transactions" value={String(totals.count)} />
            </div>
          ) : (
            <div className="pk-tiles">
              <StatTile label="Spent so far" value={txAmount(totals.spent)} />
              <StatTile label="Income so far" value={txAmount(totals.income)} />
              <StatTile label="Not counted" value={txAmount(totals.not_counted)} />
            </div>
          ))}

          {reviewCount > 0 && !focus && (
            <Alert action="Review" onAction={() => onTab?.('review')}>
              {reviewCount === 1 ? '1 transaction needs a look.'
                : `${reviewCount} transactions need a look.`}
              {' '}Sorting them keeps your numbers right.
            </Alert>
          )}

          {anySuggested && (
            <div className="tx-legend">
              <CategoryChip label="Groceries" suggested />
              <span>Pearl suggested this category. Open the transaction to confirm or change it.</span>
            </div>
          )}

          {rows.length > 0 && (
            <section className="pk-list" aria-label={title}>
              {days.map((d) => (
                <div key={d.date} role="group" aria-label={dayLabel(d.date)}>
                  <DayHeader>{dayLabel(d.date)}</DayHeader>
                  {d.rows.map((r) => (
                    <TxRow key={r.id} name={r.merchant} logo={r.logo}
                           meta={r.account + (r.pending ? ' · Pending' : '')}
                           note={r.note || r.my_note} noteLink={r.note_link}
                           chip={r.chip} amount={r.amount} inflow={r.inflow}
                           muted={r.counts === 'none'} onOpen={() => open(r.id)} />
                  ))}
                </div>
              ))}
              {more > 0 && (
                <div className="tx-more">
                  <PButton variant="text" disabled={loadingMore} onClick={showMore}>
                    Show {more} more
                  </PButton>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Nothing to show (TX-03). A search that found nothing offers to clear the
 * search and keep the filters; filters that found nothing offer to clear them.
 * Never in an error colour: an empty list is an answer, not a failure.
 */
function Empty({ filters, q, filtered, onClearSearch, onClearFilters }) {
  if (q) {
    return (
      <EmptyState title={`Nothing matches “${q}”`} action="Clear search" onAction={onClearSearch}
                  extra={filtered && (
                    <PButton variant="text" onClick={onClearFilters}>Clear filters</PButton>
                  )}>
        Try a shorter word, or check the month and account filters. We search merchant
        names, notes and amounts.
      </EmptyState>
    );
  }
  if (filtered) {
    return (
      <EmptyState icon="list" title="Nothing for these filters" action="Clear filters"
                  onAction={onClearFilters}>
        Try another month, account or category.
      </EmptyState>
    );
  }
  return (
    <EmptyState icon="list" title={`No transactions in ${monthName(filters.month)} yet`}>
      They’ll show up here as soon as your bank sends them.
    </EmptyState>
  );
}
