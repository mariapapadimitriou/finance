import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionToast, Alert, Avatar, CategoryChip, DayHeader, EmptyState, FilterChip, PButton, SearchField,
  StatTile, Toast, TxRow, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import TransactionDetail, { AddTransaction } from './TransactionDetail.jsx';
import { BatchPicker, KeyHints, SelectedBar, ShortcutsPanel } from './KeyboardReview.jsx';
import { BatchMarkPanel, BatchTagPanel } from './BatchPanels.jsx';
import { duplicateAlert } from './Duplicates.jsx';
import {
  initialState, isTextTarget, keyAction, reduce, rowName, selectRange, targets,
} from './keyboardKeys.js';
import { ErrorNote } from '../components/ui.jsx';
import {
  accountTitle, batchCategory, batchConfirm, excludeTransaction, getAccountsOverview,
  getPreferences, getTxList, savePreferences, setOneOff, undoChange,
} from '../api.js';
import { readTxUrl, writeTxUrl } from '../router.js';

/**
 * Transactions (Pearl TX-01 to TX-03, THL-122).
 *
 * Opens on this calendar month, every account and every category, newest
 * first, grouped by day. Search and the filters combine, and live in the
 * address bar so a filtered list can be linked to and survives back and
 * forward. What each row says — its amount, whether it counts, its chip and
 * its note — comes from the server, so the list and the month never disagree.
 *
 * Opened on a group, a category, a tag or a merchant (TX-02), the title
 * names it and the tiles compare it with a usual month. With nothing to show
 * (TX-03) the filters stay in view so she can see why, and nothing is drawn
 * in an error colour.
 *
 * What was this? (2026-10-14): clicking a row opens the transaction, whose
 * Mark as… is the same sheet Needs a look uses; nothing appears on hover. A
 * chip a rule decided wears a lock. Select mode works on a phone as well as
 * a desktop, and the selected bar can change the category, mark the
 * selection as something, tag it, leave it out or confirm it, with one Undo.
 * More filters: what counts, an amount range, a tag, pending only, needs a
 * look only; a month or every month; and the list folded by merchant or by
 * category.
 *
 * A one-off (THL-71 U-02) says so on its row. The second copy of a likely
 * duplicate (THL-165 D-01) is listed as not counted, with an alert that
 * leads to the question; each copy says where it came from.
 *
 * On a desktop (≥1,024px) the list is also a keyboard review (THL-83 K-01
 * to K-04): rows are one tab stop with a roving focus, each has a checkbox,
 * and the keys in `keyboardKeys.js` move, select, confirm, change, mark
 * one-offs, open and undo — only while the list has focus.
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

export function monthName(month, withYear = false) {
  if (month === 'all') return 'All months';
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

// The amount ranges on offer, as "min-max" in the address bar.
export const AMOUNTS = [
  { value: '', label: 'Any amount' },
  { value: '0-20', label: 'Under $20' },
  { value: '20-100', label: '$20 to $100' },
  { value: '100-500', label: '$100 to $500' },
  { value: '500-', label: 'Over $500' },
];
export const COUNTS = [
  { value: '', label: 'Everything' },
  { value: 'spending', label: 'Spending' },
  { value: 'income', label: 'Income' },
  { value: 'none', label: 'Not counted' },
];
export const VIEWS = [
  { value: '', label: 'By day' },
  { value: 'merchant', label: 'By merchant' },
  { value: 'category', label: 'By category' },
];

/** "0-20" → {amount_min, amount_max} for the request. */
export function amountRange(value) {
  if (!value) return {};
  const [lo, hi] = value.split('-');
  const out = {};
  if (lo) out.amount_min = lo;
  if (hi) out.amount_max = hi;
  return out;
}

/** The filters, from the address bar, with the defaults filled in. */
function fromUrl() {
  const url = readTxUrl();
  const f = url?.filters ?? {};
  return { month: f.month || thisMonth(), account: f.account || '', group: f.group || '',
           category: f.category || '', excluded: f.excluded || '', joint: f.joint || '',
           recurring: f.recurring || '', q: f.q || '',
           tag: f.tag || '', counts: f.counts || '', amount: f.amount || '',
           pending: f.pending || '', look: f.look || '', merchant: f.merchant || '',
           by: f.by || '',
           from: url?.from || '' };
}

const DEFAULTS = () => ({ month: thisMonth(), account: '', group: '', category: '',
                          excluded: '', joint: '', recurring: '', from: '',
                          tag: '', counts: '', amount: '', pending: '', look: '', merchant: '',
                          by: '' });

/**
 * The Account filter's options: the same accounts, names and order as
 * Profile › Accounts (nicknames, last four digits), without the ones that
 * have nothing to list — balance-only investments, balances added by hand,
 * accounts removed. Falls back to the ledger's own list until the overview
 * arrives.
 */
export function accountOptionsFrom(overview, accounts) {
  const out = [{ value: '', label: 'All accounts' }];
  if (overview) {
    const rows = [...(overview.linked ?? []), ...(overview.added ?? [])]
      .filter((a) => a.transactions > 0 && a.source !== 'hand' && a.kind !== 'investment');
    const names = new Map();
    rows.forEach((a) => names.set(a.name, (names.get(a.name) ?? 0) + 1));
    const label = (a) => {
      const base = (names.get(a.name) > 1 && a.institution && !a.nickname)
        ? `${a.institution} ${a.name}` : a.name;
      return `${base}${a.mask ? ` ••${a.mask}` : ''}${a.joint ? ' · Joint' : ''}`;
    };
    const linked = rows.filter((a) => a.source === 'plaid').map((a) => ({ value: a.id, label: label(a) }));
    const added = rows.filter((a) => a.source !== 'plaid').map((a) => ({ value: a.id, label: label(a) }));
    if (linked.length && added.length) {
      out.push({ group: 'Linked', options: linked }, { group: 'Added by you', options: added });
    } else {
      out.push(...linked, ...added);
    }
    return out;
  }
  return [...out, ...accounts.map((a) => ({ value: a.account_id, label: accountTitle(a) }))];
}

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
  const [overview, setOverview] = useState(null);
  const request = useRef(0);
  // Keyboard review (THL-83): focus and selection, the batch picker, the
  // shortcuts panel, and her single-key preference. Select mode on a phone
  // uses the same selection (2026-10-14).
  const desktop = useDesktop();
  const [selecting, setSelecting] = useState(false);
  const [kb, setKb] = useState(initialState);
  const [picking, setPicking] = useState(null);
  const [marking, setMarking] = useState(null);
  const [tagging, setTagging] = useState(null);
  const [help, setHelp] = useState(false);
  const [singleKey, setSingleKey] = useState(true);
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);
  const searchRef = useRef(null);
  const moved = useRef(false);
  // The last change with an Undo, for Ctrl/⌘+Z once its toast has gone.
  const lastChange = useRef(null);
  const selectable = desktop || selecting;

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

  // The accounts as Profile › Accounts lists them, for the filter.
  useEffect(() => {
    let live = true;
    getAccountsOverview().then((d) => { if (live) setOverview(d); }).catch(() => {});
    return () => { live = false; };
  }, [version]);

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
    || !!filters.recurring || !!filters.tag || !!filters.counts || !!filters.amount
    || !!filters.pending || !!filters.look || !!filters.merchant;
  // Back to TX-01's defaults; the search, if any, is its own control.
  const clearFilters = () => choose(DEFAULTS());
  const clearSearch = () => { setQuery(''); choose({ q: '' }); };

  const fetchPage = useCallback(async (offset) => {
    const id = ++request.current;
    try {
      const { from, amount, by, ...params } = filters;
      const res = await getTxList({ ...params, ...amountRange(amount), by: by || '',
                                    limit: PAGE, offset });
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
    if (filters.month && filters.month !== 'all') months.add(filters.month);
    return [...[...months].sort().reverse().map((m) => ({ value: m, label: monthName(m) })),
            { value: 'all', label: 'All months' }];
  }, [summary, filters.month]);

  const accountOptions = useMemo(() => accountOptionsFrom(overview, accounts), [overview, accounts]);

  const groups = data?.groups ?? { essentials: 'Essentials', lifestyle: 'Lifestyle',
    income: 'Income', savings: 'Savings', transfer: 'Transfer' };
  const categoryOptions = useMemo(() => [
    { value: '', label: 'All categories' },
    { group: 'Groups', options: Object.entries(groups).map(([k, v]) => ({ value: `g:${k}`, label: v })) },
    { group: 'Kind', options: Object.entries(data?.kinds ?? { fixed: 'Fixed', variable: 'Variable' })
        .map(([k, v]) => ({ value: `g:${k}`, label: v })) },
    { group: 'Categories', options: categories
        .filter((c) => !c.hidden || c.name === filters.category)
        .map((c) => ({ value: `c:${c.name}`, label: c.name })) },
    // Rows you excluded are not in the list; this is where they can be found
    // and put back.
    // So are a joint account's rows that are someone else's, until she says
    // one was hers.
    { group: 'Other', options: [
      { value: 'x:excluded', label: 'Left out' },
      { value: 'x:recurring', label: 'Subscriptions' },
      ...(accounts.some((a) => a.joint) ? [{ value: 'x:joint', label: 'Joint: not yours' }] : []),
    ] },
  ], [categories, groups, accounts, filters.category]);
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
  const tagOptions = useMemo(() => [
    { value: '', label: 'Any tag' },
    ...(data?.tags ?? []).map((t) => ({ value: t, label: t })),
  ], [data?.tags]);
  const showTags = (data?.tags?.length ?? 0) > 0 || !!filters.tag;

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
  const focus = data?.focus;           // set when a group, category, tag or merchant is chosen
  const view = filters.by || '';
  const more = view ? 0 : (data?.total ?? 0) - rows.length;
  const empty = !!data && (data.total ?? 0) === 0;
  const anySuggested = rows.some((r) => r.suggested);
  const anyRuled = rows.some((r) => r.ruled);
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

  // ── Selection (THL-83, and select mode on a phone) ────────────────────
  const ids = useMemo(() => rows.map((r) => r.id), [rows]);
  const byId = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);
  const selected = kb.selected.filter((id) => byId.has(id));
  const clearSelection = () => setKb((k) => reduce(k, 'clear', ids));

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
    clearSelection();
    focusRow();
    saved({ change: { ids: targetIds, title: res.title, detail: res.detail, undo: res.undo } });
  });

  const confirmRows = (targetIds) => {
    const usable = targetIds.filter((id) => byId.get(id)?.suggested);
    if (!usable.length) { setToast('Nothing to confirm'); return; }
    run(() => batchConfirm(usable), (res) => {
      clearSelection();
      if (res.undo) saved({ change: { ids: res.confirmed, title: res.title, detail: res.detail,
                                      undo: res.undo } });
      else setToast(res.title);
    });
  };

  // The selection answered at once (Mark as…, Tag): the panel's answer is
  // already a toast with Undo.
  const batchDone = (targetIds) => (res) => {
    setMarking(null);
    setTagging(null);
    clearSelection();
    saved({ change: { ids: targetIds, title: res.title, detail: res.detail, undo: res.undo } });
  };

  const leaveOut = (targetIds) => run(async () => {
    for (const id of targetIds) await excludeTransaction(id, 'Left out from the list');
    return targetIds.length;
  }, (n) => {
    clearSelection();
    setToast(n === 1 ? 'Left out. Find it under Left out in the category filter.'
      : `Left ${n} out. Find them under Left out in the category filter.`);
  });

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
    if (!desktop || picking || marking || tagging || help) return;
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
  const focusLabel = filters.group ? groups[filters.group]
    : filters.category || filters.tag || filters.merchant || special;
  const title = focusLabel ? (filters.month === 'all' ? `${focusLabel}, all months`
    : `${focusLabel} in ${monthName(filters.month)}`) : 'Transactions';
  const overline = filters.from === 'home' ? 'From Home' : monthName(filters.month, true);
  const anySelected = selected.length > 0 && selectable;

  return (
    <div className="pk tx-page">
      <header className="tx-head">
        <div>
          <p className="pk-overline accent">{overline}</p>
          <h1 className="pk-h1">{title}</h1>
        </div>
        <div className="tx-head-actions">
          {!desktop && rows.length > 0 && (
            <PButton variant="secondary" aria-pressed={selecting}
                     onClick={() => { setSelecting((s) => !s); clearSelection(); }}>
              {selecting ? 'Done' : 'Select'}
            </PButton>
          )}
          <PButton onClick={() => setAdding(true)}>
            <PIcon name="plus" size={16} /> Add a transaction
          </PButton>
        </div>
      </header>

      {anySelected ? (
        <SelectedBar count={selected.length} singleKey={desktop && singleKey}
                     onChange={() => setPicking(selected)}
                     onMark={() => setMarking(selected)}
                     onTag={() => setTagging(selected)}
                     onLeaveOut={() => leaveOut(selected)}
                     onConfirm={() => confirmRows(selected)}
                     onClear={clearSelection} />
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
          <FilterChip label="Counts" value={filters.counts} options={COUNTS}
                      active={!!filters.counts} onChange={(v) => choose({ counts: v })} />
          <FilterChip label="Amount" value={filters.amount} options={AMOUNTS}
                      active={!!filters.amount} onChange={(v) => choose({ amount: v })} />
          {showTags && (
            <FilterChip label="Tag" value={filters.tag} options={tagOptions}
                        active={!!filters.tag} onChange={(v) => choose({ tag: v })} />
          )}
          <button type="button" className={`pk-filter tx-toggle${filters.pending ? ' active' : ''}`}
                  aria-pressed={!!filters.pending}
                  onClick={() => choose({ pending: filters.pending ? '' : '1' })}>
            Pending
          </button>
          <button type="button" className={`pk-filter tx-toggle${filters.look ? ' active' : ''}`}
                  aria-pressed={!!filters.look}
                  onClick={() => choose({ look: filters.look ? '' : '1' })}>
            Needs a look
          </button>
          <FilterChip label="View" value={filters.by} options={VIEWS}
                      active={!!filters.by} onChange={(v) => choose({ by: v })} />
          {filters.merchant && (
            <button type="button" className="pk-filter active tx-toggle" aria-pressed="true"
                    onClick={() => choose({ merchant: '' })}>
              {filters.merchant} <PIcon name="x" size={14} />
            </button>
          )}
          {filtered && !empty && (
            <PButton variant="text" className="tx-clear" onClick={clearFilters}>
              Clear filters
            </PButton>
          )}
        </div>
      </div>
      )}

      {picking && (
        <BatchPicker ids={picking} categories={categories.filter((c) => !c.hidden)} busy={busy}
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
              <StatTile label={filters.month === 'all' ? `${focus.label} in all` : `${focus.label} so far`}
                        value={txAmount(focus.total)} />
              <StatTile label="In a usual month"
                        value={focus.usual == null ? '—' : txAmount(focus.usual)} />
              <StatTile label="Transactions" value={String(totals.count)} />
            </div>
          ) : (
            <div className="pk-tiles">
              <StatTile label={filters.month === 'all' ? 'Spent' : 'Spent so far'} value={txAmount(totals.spent)} />
              <StatTile label={filters.month === 'all' ? 'Income' : 'Income so far'} value={txAmount(totals.income)} />
              <StatTile label="Not counted" value={txAmount(totals.not_counted)} />
            </div>
          ))}

          {reviewCount > 0 && !focus && !filters.look && (
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

          {view === 'merchant' && data?.merchants && (
            <FoldedList rows={data.merchants} kind="merchant"
                        onPick={(m) => choose({ merchant: m.merchant, by: '' })} />
          )}
          {view === 'category' && data?.categories && (
            <FoldedList rows={data.categories} kind="category"
                        onPick={(c) => choose({ category: c.category, group: '', by: '' })} />
          )}

          {!view && (anySuggested || anyRuled) && (
            <div className="tx-legend">
              {anySuggested && (
                <>
                  <CategoryChip label="Groceries" suggested />
                  <span>Pearl isn’t sure of this one. Open it to confirm or change.</span>
                </>
              )}
              {anyRuled && (
                <>
                  <CategoryChip label="Coffee" ruled />
                  <span>From a rule of yours.</span>
                </>
              )}
            </div>
          )}

          {desktop && !view && rows.length > 0 && !anySelected && (
            <KeyHints singleKey={singleKey} />
          )}

          {!view && rows.length > 0 && (
            <section className={`pk-list${desktop ? ' tx-keys' : ''}${selectable ? ' tx-selectable' : ''}`}
                     aria-label={title}
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
                             tags={r.tags ?? []} ruled={r.ruled}
                             muted={r.counts === 'none'} flash={flash.has(r.id)}
                             onOpen={() => openRow(r)}
                             {...(desktop ? {
                               tabIndex: index.get(r.id) === Math.min(kb.focus, ids.length - 1) ? 0 : -1,
                               'data-row-index': index.get(r.id),
                               onFocus: () => setKb((k) => ({ ...k, focus: index.get(r.id) })),
                             } : {})} />
                    );
                    const on = selected.includes(r.id);
                    const i = index.get(r.id);
                    return (
                      <div key={r.id}
                           className={`tx-sel${on ? ' on' : ''}${flash.has(r.id) ? ' flash' : ''}`}>
                        {selectable && (
                          <label className="tx-check">
                            <input type="checkbox" tabIndex={-1} checked={on} onChange={() => {}}
                                   onClick={(e) => onCheck(e, i)}
                                   aria-label={`Select ${rowName(r, txAmount(r.amount, { inflow: r.inflow, signed: true }))}`} />
                            <span className="tx-check-box" aria-hidden="true">
                              {on && <PIcon name="check" size={14} />}
                            </span>
                          </label>
                        )}
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

          {desktop && !view && rows.length > 0 && (
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
        <AddTransaction categories={categories.filter((c) => !c.hidden)} onClose={() => setAdding(false)}
                        onSaved={() => { setAdding(false); saved(); }} />
      )}
      {marking && (
        <BatchMarkPanel ids={marking} categories={categories} onDone={batchDone(marking)}
                        onClose={() => setMarking(null)} />
      )}
      {tagging && (
        <BatchTagPanel ids={tagging} onDone={batchDone(tagging)} onClose={() => setTagging(null)} />
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

/** The list folded by merchant or by category (2026-10-14): one line each,
 * biggest spending first; picking one opens its rows. */
export function FoldedList({ rows, kind, onPick }) {
  return (
    <section className="pk-list tx-folded" aria-label={kind === 'merchant' ? 'By merchant' : 'By category'}>
      {rows.map((g) => {
        const name = kind === 'merchant' ? g.merchant : g.category;
        const main = g.spent >= 0.005 || (g.income < 0.005 && g.not_counted < 0.005)
          ? { amount: g.spent, inflow: false, muted: false }
          : g.income >= 0.005 ? { amount: g.income, inflow: true, muted: false }
            : { amount: g.not_counted, inflow: false, muted: true };
        const bits = [`${g.count} transaction${g.count === 1 ? '' : 's'}`];
        if (g.spent >= 0.005 && g.income >= 0.005) bits.push(`${txAmount(g.income)} in`);
        if (g.not_counted >= 0.005 && !main.muted) bits.push(`${txAmount(g.not_counted)} not counted`);
        return (
          <button type="button" key={name} className={`pk-row${main.muted ? ' muted' : ''}`}
                  onClick={() => onPick(g)}>
            {kind === 'merchant' ? <Avatar name={name} logo={g.logo} />
              : <span className="pk-avatar" aria-hidden="true"><PIcon name="list" size={16} /></span>}
            <span className="pk-row-text">
              <span className="pk-row-name">{name}</span>
              <span className="pk-row-meta">{bits.join(' · ')}</span>
            </span>
            <span className={`pk-amt ${main.muted ? 'muted' : main.inflow ? 'in' : 'out'}`}>
              {txAmount(main.amount, { inflow: main.inflow && !main.muted, signed: !main.muted && !main.inflow })}
            </span>
            <PIcon name="chevronRight" size={16} />
          </button>
        );
      })}
    </section>
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
