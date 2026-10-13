import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionToast, Alert, CategoryChip, DayHeader, EmptyState, FilterChip, PButton, SearchField,
  StatTile, Toast, TxRow, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import TransactionDetail, { AddTransaction } from './TransactionDetail.jsx';
import { BatchPicker, KeyHints, SelectedBar, ShortcutsPanel } from './KeyboardReview.jsx';
import { duplicateAlert } from './Duplicates.jsx';
import {
  initialState, isTextTarget, keyAction, reduce, rowName, selectRange, targets,
} from './keyboardKeys.js';
import { ErrorNote } from '../components/ui.jsx';
import {
  accountTitle, batchCategory, batchConfirm, getPreferences, getTxList, savePreferences,
  setOneOff, undoChange,
} from '../api.js';
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
 *
 * A one-off (THL-71 U-02) says so on its row. The second copy of a likely
 * duplicate (THL-165 D-01) is listed as not counted, with an alert that
 * leads to the question; each copy says where it came from.
 *
 * On a desktop (≥1,024px) the list is also a keyboard review (THL-83 K-01
 * to K-04): rows are one tab stop with a roving focus, each has a checkbox,
 * and the keys in `keyboardKeys.js` move, select, confirm, change, mark
 * one-offs, open and undo — only while the list has focus. Several selected
 * swap the toolbar for the selected bar; their new category is one batch
 * with one Undo, and never a merchant rule.
 */

const DESKTOP = '(min-width: 1024px)';

/** Keyboard review is for a desktop-sized window. */
function useDesktop() {
  const [on, setOn] = useState(() => typeof window !== 'undefined'
    && !!window.matchMedia?.(DESKTOP).matches);
  useEffect(() => {
    const m = window.matchMedia?.(DESKTOP);
    if (!m) return undefined;
    const update = () => setOn(m.matches);
    m.addEventListener?.('change', update);
    return () => m.removeEventListener?.('change', update);
  }, []);
  return on;
}

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
           category: f.category || '', excluded: f.excluded || '', joint: f.joint || '',
           recurring: f.recurring || '', q: f.q || '',
           from: url?.from || '' };
}

const DEFAULTS = () => ({ month: thisMonth(), account: '', group: '', category: '',
                          excluded: '', joint: '', recurring: '', from: '' });

export default function TransactionsList({ summary, categories, accounts, reviewCount = 0,
                                           onTab, onChanged, version }) {
  const [filters, setFilters] = useState(fromUrl);
  // The transaction open in the side panel (TX-04), from /transactions/<id>.
  const [openId, setOpenId] = useState(() => readTxUrl()?.id ?? null);
  const [toast, setToast] = useState('');
  // A change that moved a number (R-03): what it did, with Undo.
  const [change, setChange] = useState(null);
  // Rows that just changed, highlighted for a moment.
  const [flash, setFlash] = useState(() => new Set());
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState(filters.q);
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const request = useRef(0);
  // Keyboard review (THL-83): focus and selection, the batch picker, the
  // shortcuts panel, and her single-key preference.
  const desktop = useDesktop();
  const [kb, setKb] = useState(initialState);
  const [picking, setPicking] = useState(null);
  const [help, setHelp] = useState(false);
  const [singleKey, setSingleKey] = useState(true);
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);
  const searchRef = useRef(null);
  const moved = useRef(false);
  // The last change with an Undo, for Ctrl/⌘+Z once its toast has gone.
  const lastChange = useRef(null);

  // The address bar follows the filters. Defaults stay out of it, so the
  // plain list is just /transactions.
  const urlFilters = (f) => ({ ...f, month: f.month === thisMonth() ? '' : f.month });
  const toUrl = (f, push = false, id = openId) =>
    writeTxUrl({ id, filters: urlFilters(f), from: f.from }, { push });
  useEffect(() => { toUrl(filters); }, [filters]);

  // Back and forward move between filter states.
  useEffect(() => {
    const onPop = () => {
      if (!readTxUrl()) return;
      const next = fromUrl();
      setFilters(next);
      setQuery(next.q);
      setOpenId(readTxUrl()?.id ?? null);
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
    || !!filters.group || !!filters.category || !!filters.excluded || !!filters.joint
    || !!filters.recurring;
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
    // Rows you excluded are not in the list; this is where they can be found
    // and put back.
    // So are a joint account's rows that are someone else's, until she says
    // one was hers.
    { group: 'Other', options: [
      { value: 'x:excluded', label: 'Left out' },
      { value: 'x:recurring', label: 'Subscriptions' },
      ...(accounts.some((a) => a.joint) ? [{ value: 'x:joint', label: 'Joint: not yours' }] : []),
    ] },
  ], [categories, groups, accounts]);
  // "Review subscriptions" (THL-63) opens the list on their charges.
  const special = filters.excluded ? 'Left out' : filters.joint ? 'Joint: not yours'
    : filters.recurring ? 'Subscriptions' : '';
  const categoryValue = filters.group ? `g:${filters.group}`
    : filters.category ? `c:${filters.category}`
      : filters.excluded ? 'x:excluded' : filters.joint ? 'x:joint'
        : filters.recurring ? 'x:recurring' : '';
  const categoryLabel = filters.group ? groups[filters.group]
    : filters.category || special || 'All categories';
  const pickCategory = (v) => choose({
    group: v.startsWith('g:') ? v.slice(2) : '',
    category: v.startsWith('c:') ? v.slice(2) : '',
    excluded: v === 'x:excluded' ? '1' : '',
    joint: v === 'x:joint' ? '1' : '',
    recurring: v === 'x:recurring' ? '1' : '',
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
  const dupes = data?.duplicates ?? 0;
  const index = new Map(rows.map((r, i) => [r.id, i]));
  const open = (id) => { setOpenId(id); toUrl(filters, true, id); };
  const close = () => { setOpenId(null); toUrl(filters, true, null); };
  // After a change in the panel: say so, and refresh everything that counts
  // it (the list, the totals, the review badge).
  const saved = ({ close: closing, change: what } = {}) => {
    if (what) {
      setToast('');
      setChange(what);
      if (what.undo) lastChange.current = what;
      setFlash(new Set([what.id, ...(what.ids ?? []),
                        ...(what.undo?.rows ?? []).map((r) => r.id)].filter(Boolean)));
    } else {
      setToast('Saved');
    }
    if (closing) close();
    onChanged?.();
  };
  useEffect(() => {
    if (!flash.size) return undefined;
    const t = setTimeout(() => setFlash(new Set()), 2600);
    return () => clearTimeout(t);
  }, [flash]);
  const undo = async (what = change ?? lastChange.current) => {
    if (!what?.undo) return;
    setChange(null);
    lastChange.current = null;
    try {
      await undoChange(what.undo);
      setFlash(new Set([what.id, ...(what.ids ?? [])].filter(Boolean)));
      setToast('Undone');
    } catch (e) {
      setError(e);
    }
    onChanged?.();
  };

  // ── Keyboard review (THL-83) ──────────────────────────────────────────
  const ids = useMemo(() => rows.map((r) => r.id), [rows]);
  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);
  const selected = kb.selected.filter((id) => byId.has(id));

  useEffect(() => {
    if (!desktop) return undefined;
    let live = true;
    getPreferences().then((p) => { if (live) setSingleKey(p.single_key_shortcuts !== false); })
      .catch(() => {});
    return () => { live = false; };
  }, [desktop]);

  // Moving with the keys moves focus too: the row is one tab stop.
  useEffect(() => {
    if (!moved.current) return;
    moved.current = false;
    listRef.current?.querySelector(`[data-row-index="${kb.focus}"]`)?.focus();
  }, [kb.focus]);

  const toggleShortcuts = async (on) => {
    setSingleKey(on);
    try { await savePreferences({ single_key_shortcuts: on }); } catch (e) { setError(e); }
  };

  // A pending duplicate's question is in Needs a look (D-01 → D-02).
  const openRow = (r) => (r.duplicate?.state === 'pending' ? onTab?.('review') : open(r.id));

  async function run(fn, after) {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      after?.(res);
      onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  // K-03: one toast, one Undo, for the whole batch; rows flash, the
  // selection clears and focus stays where it was.
  const focusRow = () => setTimeout(() => {
    listRef.current?.querySelector('.pk-row[tabindex="0"]')?.focus();
  }, 0);
  const applyCategory = (targetIds, category) => run(() => batchCategory(targetIds, category), (res) => {
    setPicking(null);
    setKb((k) => ({ ...k, selected: [], anchor: null }));
    focusRow();
    saved({ change: { ids: targetIds, title: res.title, detail: res.detail, undo: res.undo } });
  });

  const confirmRows = (targetIds) => {
    const usable = targetIds.filter((id) => byId.get(id)?.suggested);
    if (!usable.length) { setToast('Nothing to confirm'); return; }
    run(() => batchConfirm(usable), (res) => {
      setKb((k) => ({ ...k, selected: [], anchor: null }));
      if (res.undo) saved({ change: { ids: res.confirmed, title: res.title, detail: res.detail,
                                      undo: res.undo } });
      else setToast(res.title);
    });
  };

  const toggleOneOff = (r) => {
    if (!r.can_one_off) {
      setToast('Transfers and repayments already stay out of your usual month');
      return;
    }
    run(() => setOneOff(r.id, !r.one_off), (res) => {
      saved({ change: { id: r.id, title: res.title, detail: res.detail, undo: res.undo } });
    });
  };

  const onListKey = (e) => {
    if (!desktop || picking || help) return;
    const action = keyAction(e, { singleKey, inText: isTextTarget(e.target) });
    if (!action) return;
    e.preventDefault();
    const focused = byId.get(ids[Math.min(kb.focus, ids.length - 1)]);
    switch (action) {
      case 'open':
        if (focused) openRow(focused);
        return;
      case 'search':
        searchRef.current?.focus();
        return;
      case 'help':
        setHelp(true);
        return;
      case 'undo':
        undo();
        return;
      case 'change': {
        const t = targets(kb, ids);
        if (t.length) setPicking(t);
        return;
      }
      case 'confirm':
        confirmRows(targets(kb, ids));
        return;
      case 'oneoff':
        if (focused) toggleOneOff(focused);
        return;
      default:
        moved.current = action !== 'clear' && action !== 'select';
        setKb((k) => reduce(k, action, ids));
    }
  };

  const onCheck = (e, i) => {
    e.preventDefault();
    if (e.shiftKey) setKb((k) => selectRange(k, ids, i));
    else setKb((k) => reduce({ ...k, focus: i }, 'select', ids));
  };

  // The title says what the list is: "Lifestyle in October" when it is one
  // group or category, otherwise just Transactions.
  const focusLabel = filters.group ? groups[filters.group] : filters.category || special;
  const title = focusLabel ? `${focusLabel} in ${monthName(filters.month)}` : 'Transactions';
  const overline = filters.from === 'home' ? 'From Home' : monthName(filters.month, true);

  return (
    <div className="pk tx-page">
      <header className="tx-head">
        <div>
          <p className="pk-overline accent">{overline}</p>
          <h1 className="pk-h1">{title}</h1>
        </div>
        <PButton variant="text" onClick={() => setAdding(true)}>Add a transaction</PButton>
      </header>

      {desktop && selected.length > 0 ? (
        <SelectedBar count={selected.length} singleKey={singleKey}
                     onChange={() => setPicking(selected)}
                     onConfirm={() => confirmRows(selected)}
                     onClear={() => setKb((k) => reduce(k, 'clear', ids))} />
      ) : (
      <div className="tx-toolbar">
        <SearchField value={query} onChange={setQuery} label="Search transactions"
                     placeholder="Search merchants or amounts" inputRef={searchRef}
                     aria-keyshortcuts={desktop && singleKey ? '/' : undefined} />
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
      )}

      {desktop && picking && (
        <BatchPicker ids={picking} categories={categories} busy={busy}
                     onApply={(cat) => applyCategory(picking, cat)}
                     onClose={() => { setPicking(null); focusRow(); }} />
      )}

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
              {dupes > 0 ? duplicateAlert(dupes) : (
                <>
                  {reviewCount === 1 ? '1 transaction needs a look.'
                    : `${reviewCount} transactions need a look.`}
                  {' '}Sorting them keeps your numbers right.
                </>
              )}
            </Alert>
          )}

          {anySuggested && (
            <div className="tx-legend">
              <CategoryChip label="Groceries" suggested />
              <span>Pearl suggested this category. Open the transaction to confirm or change it.</span>
            </div>
          )}

          {desktop && rows.length > 0 && !(selected.length > 0) && (
            <KeyHints singleKey={singleKey} />
          )}

          {rows.length > 0 && (
            <section className={`pk-list${desktop ? ' tx-keys' : ''}`} aria-label={title}
                     ref={listRef} onKeyDown={onListKey}
                     aria-describedby={desktop ? 'tx-keys-help' : undefined}>
              {desktop && (
                <p className="pk-sr" id="tx-keys-help">
                  {singleKey ? 'Use the arrow keys or J and K to move, X to select, Y to confirm, '
                    + 'C to change the category, U for a one-off and question mark for every shortcut.'
                    : 'Use the arrow keys to move and Shift with the arrow keys to select.'}
                </p>
              )}
              {days.map((d) => (
                <div key={d.date} role="group" aria-label={dayLabel(d.date)}>
                  <DayHeader>{dayLabel(d.date)}</DayHeader>
                  {d.rows.map((r) => {
                    const row = (
                      <TxRow key={r.id} name={r.merchant} logo={r.logo}
                             meta={r.account + (r.pending ? ' · Pending' : '')
                               + (r.source_label ? ` · ${r.source_label}` : '')}
                             note={r.note || r.my_note} noteLink={r.note_link}
                             chip={r.chip} amount={r.amount} inflow={r.inflow}
                             muted={r.counts === 'none'} flash={flash.has(r.id)}
                             onOpen={() => openRow(r)}
                             {...(desktop ? {
                               tabIndex: index.get(r.id) === Math.min(kb.focus, ids.length - 1) ? 0 : -1,
                               'data-row-index': index.get(r.id),
                               onFocus: () => setKb((k) => ({ ...k, focus: index.get(r.id) })),
                             } : {})} />
                    );
                    if (!desktop) return row;
                    const on = selected.includes(r.id);
                    const i = index.get(r.id);
                    return (
                      <div key={r.id} className={`tx-sel${on ? ' on' : ''}${flash.has(r.id) ? ' flash' : ''}`}>
                        <label className="tx-check">
                          <input type="checkbox" tabIndex={-1} checked={on} onChange={() => {}}
                                 onClick={(e) => onCheck(e, i)}
                                 aria-label={`Select ${rowName(r, txAmount(r.amount, { inflow: r.inflow }))}`} />
                          <span className="tx-check-box" aria-hidden="true">
                            {on && <PIcon name="check" size={14} />}
                          </span>
                        </label>
                        {row}
                      </div>
                    );
                  })}
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

          {desktop && rows.length > 0 && (
            <PButton variant="text" className="tx-keys-link" onClick={() => setHelp(true)}
                     aria-keyshortcuts={singleKey ? '?' : undefined}>
              Keyboard shortcuts
            </PButton>
          )}
        </>
      )}

      {openId && (
        <TransactionDetail id={openId} initial={rows.find((r) => r.id === openId)}
                           categories={categories} onClose={close} onSaved={saved} />
      )}
      {adding && (
        <AddTransaction categories={categories} onClose={() => setAdding(false)}
                        onSaved={() => { setAdding(false); saved(); }} />
      )}
      {change && (
        <ActionToast title={change.title} detail={change.detail}
                     onUndo={change.undo ? () => undo() : undefined}
                     onDone={() => setChange(null)} />
      )}
      {toast && !change && <Toast onDone={() => setToast('')}>{toast}</Toast>}
      {help && (
        <ShortcutsPanel singleKey={singleKey} onToggle={toggleShortcuts}
                        onClose={() => setHelp(false)} />
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
