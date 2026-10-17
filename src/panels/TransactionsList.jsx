import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionToast, Alert, EmptyState, FilterChip, PButton, SearchField, Toast, TxRow, txAmount,
} from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import TransactionDetail, { AddTransaction } from './TransactionDetail.jsx';
import { BatchPicker, SelectedBar, ShortcutsPanel } from './KeyboardReview.jsx';
import { BatchMarkPanel, BatchTagPanel } from './BatchPanels.jsx';
import { rangeWords } from './RangePanels.jsx';
import { TxFiltersPanel, requestFor } from './TxFilters.jsx';
import { CashFlowTabs } from './InsightsParts.jsx';
import { shortDate } from './HomePanel.jsx';
import { duplicateAlert } from './Duplicates.jsx';
import FlowCards from './FlowCards.jsx';
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
 * Cash flow › Transactions (Pearl TX-01 to TX-03, THL-122; VF-01 to VF-04,
 * DR-01, DR-02 and WW-01, THL-231).
 *
 * ALT-04 (2026-10-17): two cards first — Outflows and Inflows, the month's
 * counted flows with a line of how each built up against a three-month
 * average (FlowCards.jsx); transfers are neither. Then one row of tools:
 * Search, the month, Filters (an icon on a phone) and Add. Needs a look is
 * a banner that goes to its own page, never mixed into the list. The list
 * is by day, newest first, each day named ("Today", "Yesterday", the
 * weekday) with that day's outflows. Everything else (months, account,
 * category, kind, tags, an amount range, owed to you, show only) is in the
 * Filters panel (VF-02). Filters live
 * in the address bar so a filtered list can be linked to and survives back
 * and forward. What each row says — its amount, whether it counts, its chip
 * and its note — comes from the server, so the list and the month never
 * disagree.
 *
 * Nothing is written on hover (WW-01, 2026-10-16): a row only tints. Where
 * Pearl isn't sure, the category chip is dotted, and clicking it confirms
 * the guess in place; clicking anywhere else opens the row, where the
 * category can be changed and Mark as… (the What was this? sheet) lives.
 * Selecting several swaps in a floating bar (VF-03): Change category, Mark
 * as…, Tag, Leave out, ✓ Confirm, with one Undo. Sorting a range of days
 * moved to the calendar (CAL-06); the list can show one with ?first&last.
 *
 * With nothing to show (TX-03) the filters stay in view so she can see why,
 * and nothing is drawn in an error colour. A one-off (THL-71 U-02) says so
 * on its row. The second copy of a likely duplicate (THL-165 D-01) is
 * listed as not counted, with an alert that leads to the question.
 *
 * On a desktop (≥1,024px) the list is also a keyboard review (THL-83): rows
 * are one tab stop with a roving focus, each has a checkbox, and the keys in
 * `keyboardKeys.js` move, select, confirm, change, mark one-offs, open and
 * undo — only while the list has focus.
 */

const DESKTOP = '(min-width: 1024px)';

/** Keyboard review and hover actions are for a desktop-sized window. */
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
  if (month === 'last3') return 'Last 3 months';
  const [y, m] = month.split('-').map(Number);
  const name = MONTHS[m - 1] ?? month;
  return withYear || y !== new Date().getFullYear() ? `${name} ${y}` : name;
}

const SHORT_DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * A day's header (ALT-04): a name and a quieter date. "Today · Fri, Oct 9",
 * "Yesterday · Thu, Oct 8", "Wednesday · Oct 7" within the week, and
 * "October 2 · Friday" before that.
 */
export function dayParts(iso, now = new Date()) {
  const [y, m, d] = iso.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const ago = Math.round((today - date) / 86400000);
  const short = `${SHORT_MONTHS[m - 1]} ${d}`;
  const year = y !== now.getFullYear() ? `, ${y}` : '';
  if (ago === 0) return { name: 'Today', date: `${SHORT_DAYS[date.getDay()]}, ${short}` };
  if (ago === 1) return { name: 'Yesterday', date: `${SHORT_DAYS[date.getDay()]}, ${short}` };
  if (ago > 1 && ago < 7) return { name: WEEKDAYS[date.getDay()], date: short };
  return { name: `${MONTHS[m - 1]} ${d}${year}`, date: WEEKDAYS[date.getDay()] };
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

/** "UBER EATS · 3 PURCHASES · -$74.30" (VF-01): a group's header. */
export function groupLabel(g) {
  const n = g.count;
  const what = g.spent >= 0.005 || (g.income < 0.005 && g.not_counted < 0.005)
    ? `${n} purchase${n === 1 ? '' : 's'} · ${txAmount(g.spent, { signed: g.spent >= 0.005 })}`
    : g.income >= 0.005 ? `${n} · ${txAmount(g.income, { inflow: true })}`
      : `${n} · ${txAmount(g.not_counted)}`;
  return `${g.name} · ${what}`.toUpperCase();
}

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

/** "Priya owes you $194.20 for 2 purchases." (WW-01's second alert). */
export function owedWords(owed) {
  if (!owed || !owed.names?.length) return '';
  const names = owed.names.length === 1 ? owed.names[0]
    : `${owed.names.slice(0, -1).join(', ')} and ${owed.names[owed.names.length - 1]}`;
  const verb = owed.names.length === 1 ? 'owes' : 'owe';
  return `${names} ${verb} you ${txAmount(owed.total)} for ${owed.count} purchase${owed.count === 1 ? '' : 's'}.`;
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
           by: f.by || '', owed: f.owed || '',
           first: f.first || '', last: f.last || '',
           from: url?.from || '' };
}

const DEFAULTS = () => ({ month: thisMonth(), account: '', group: '', category: '',
                          excluded: '', joint: '', recurring: '', from: '',
                          tag: '', counts: '', amount: '', pending: '', look: '', merchant: '',
                          by: '', owed: '', day: '', first: '', last: '' });

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
  // The transaction open in the side panel (TX-04), from /transactions/<id>,
  // and the step it opens on (a row's Category or Mark as…).
  const [openId, setOpenId] = useState(() => readTxUrl()?.id ?? null);
  const [openStep, setOpenStep] = useState('main');
  const [toast, setToast] = useState('');
  // A change that moved a number (R-03): what it did, with Undo.
  const [change, setChange] = useState(null);
  // Rows that just changed, highlighted for a moment.
  const [flash, setFlash] = useState(() => new Set());
  const [adding, setAdding] = useState(false);
  const [filtering, setFiltering] = useState(false);
  const [query, setQuery] = useState(filters.q);
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [overview, setOverview] = useState(null);
  const request = useRef(0);
  // Keyboard review (THL-83): focus and selection, the batch picker, the
  // shortcuts panel, and her single-key preference. Select mode on a phone
  // uses the same selection.
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
    || !!filters.pending || !!filters.look || !!filters.merchant || !!filters.owed || !!filters.day
    || !!filters.first;
  // Back to TX-01's defaults; the search, if any, is its own control.
  const clearFilters = () => choose(DEFAULTS());
  const clearSearch = () => { setQuery(''); choose({ q: '' }); };
  // What the Filters panel holds, beyond the toolbar's three chips.
  const extra = [filters.month !== thisMonth() && !/^\d{4}-\d{2}$/.test(filters.month),
                 !!filters.account, !!(filters.group || filters.category || filters.excluded
                   || filters.joint || filters.recurring),
                 !!filters.tag, !!filters.counts, !!filters.amount, !!filters.pending, !!filters.look,
                 !!filters.owed].filter(Boolean).length;

  const fetchPage = useCallback(async (offset) => {
    const id = ++request.current;
    try {
      const res = await getTxList({ ...requestFor(filters, thisMonth()), limit: PAGE, offset });
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
    if (/^\d{4}-\d{2}$/.test(filters.month)) months.add(filters.month);
    return [...[...months].sort().reverse().map((m) => ({ value: m, label: monthName(m) })),
            { value: 'last3', label: 'Last 3 months' }, { value: 'all', label: 'All months' }];
  }, [summary, filters.month]);

  const accountOptions = useMemo(() => accountOptionsFrom(overview, accounts), [overview, accounts]);

  const groups = data?.groups ?? { essentials: 'Essentials', lifestyle: 'Lifestyle',
    income: 'Income', savings: 'Savings', transfer: 'Transfer' };
  const categoryOptions = useMemo(() => [
    { value: '', label: 'All categories' },
    { group: 'Groups', options: Object.entries(groups).map(([k, v]) => ({ value: `g:${k}`, label: v })) },
    { group: 'Categories', options: categories
        .filter((c) => !c.hidden || c.name === filters.category)
        .map((c) => ({ value: `c:${c.name}`, label: c.name })) },
    // Rows you excluded are not in the list; this is where they can be found
    // and put back. So are a joint account's rows that are someone else's,
    // until she says one was hers.
    { group: 'Other', options: [
      { value: 'x:excluded', label: 'Left out' },
      { value: 'x:recurring', label: 'Subscriptions' },
      ...(accounts.some((a) => a.joint) ? [{ value: 'x:joint', label: 'Joint: not yours' }] : []),
    ] },
  ], [categories, groups, accounts, filters.category]);
  // "Review subscriptions" (THL-63) opens the list on their charges.
  const special = filters.excluded ? 'Left out' : filters.joint ? 'Joint: not yours'
    : filters.recurring ? 'Subscriptions' : '';
  const kindGroup = ['fixed', 'variable'].includes(filters.group);
  const categoryValue = filters.group && !kindGroup ? `g:${filters.group}`
    : filters.category ? `c:${filters.category}`
      : filters.excluded ? 'x:excluded' : filters.joint ? 'x:joint'
        : filters.recurring ? 'x:recurring' : '';

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
  const view = '';                      // ALT-04: by day only
  const groupsOf = view ? (data?.groups_of ?? []) : null;
  // In a grouped view every row is on the page; the keys and selection work
  // over them in the order shown.
  const shownRows = useMemo(() => (groupsOf ? groupsOf.flatMap((g) => g.rows) : rows), [groupsOf, rows]);
  const more = view ? 0 : (data?.total ?? 0) - rows.length;
  const empty = !!data && (data.total ?? 0) === 0;
  const dupes = data?.duplicates ?? 0;
  const owed = data?.owed;
  const index = new Map(shownRows.map((r, i) => [r.id, i]));
  const open = (id, step = 'main') => { setOpenStep(step); setOpenId(id); toUrl(filters, true, id); };
  const close = () => { setOpenId(null); setOpenStep('main'); toUrl(filters, true, null); };
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
  const ids = useMemo(() => shownRows.map((r) => r.id), [shownRows]);
  const byId = useMemo(() => new Map(shownRows.map((r) => [r.id, r])), [shownRows]);
  const selected = kb.selected.filter((id) => byId.has(id));
  const clearSelection = () => setKb((k) => reduce(k, 'clear', ids));
  // "3 selected · -$148.95": what the selection comes to, money out less money in.
  const selectedTotal = useMemo(() => {
    const net = selected.reduce((sum, id) => {
      const r = byId.get(id);
      if (!r || r.counts === 'none') return sum;
      return sum + (r.inflow ? r.amount : -r.amount);
    }, 0);
    return Math.abs(net) < 0.005 ? '' : txAmount(Math.abs(net), { inflow: net > 0, signed: true });
  }, [selected, byId]);

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

  // The title: "Cash flow", with the month over it (VF-01); a focus names
  // itself in the tiles.
  const overline = filters.from === 'home' ? 'From Home' : monthName(filters.month, true);
  const anySelected = selected.length > 0 && selectable;

  // WW-01: the dotted chip confirms Pearl's guess in place; the row opens.
  const confirmable = (r) => r.suggested && r.chip?.suggested
    && r.chip.label !== 'Possible duplicate' && r.chip.label !== 'Whose?'
    && r.duplicate?.state !== 'pending';

  const rowFor = (r) => {
    const row = (
      <TxRow key={r.id} name={r.merchant} logo={r.logo}
             onConfirm={confirmable(r) ? () => confirmRows([r.id]) : undefined} busy={busy}
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
      <div key={r.id} className={`tx-sel${on ? ' on' : ''}${flash.has(r.id) ? ' flash' : ''}`}>
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
  };

  const sections = groupsOf
    ? groupsOf.map((g) => ({ key: g.name, label: groupLabel(g), rows: g.rows }))
    : days.map((d) => ({ key: d.date, label: dayLabel(d.date), rows: d.rows }));

  return (
    <div className="pk tx-page">
      <header className="tx-head">
        <div>
          <p className="pk-overline accent">{overline}</p>
          <h1 className="pk-h1">Cash flow</h1>
        </div>
        <div className="tx-head-actions">
          {!desktop && shownRows.length > 0 && (
            <PButton variant="secondary" aria-pressed={selecting}
                     onClick={() => { setSelecting((s) => !s); clearSelection(); }}>
              {selecting ? 'Done' : 'Select'}
            </PButton>
          )}
        </div>
      </header>
      <CashFlowTabs current="transactions" onTab={onTab} />

      {!empty && <FlowCards totals={totals} flows={data?.flows} />}

      <div className="tx-toolbar">
        <SearchField value={query} onChange={setQuery} label="Search transactions"
                     placeholder="Search" inputRef={searchRef}
                     aria-keyshortcuts={desktop && singleKey ? '/' : undefined} />
        <div className="tx-chips">
          <FilterChip label="Month" value={filters.month} options={monthOptions}
                      active={filters.month !== thisMonth()}
                      onChange={(v) => choose({ month: v, day: '' })} />
          <button type="button" className={`pk-filter tx-toggle tx-filters${extra ? ' active' : ''}`}
                  aria-pressed={!!extra} aria-label={extra ? `Filters, ${extra} on` : 'Filters'}
                  onClick={() => setFiltering(true)}>
            <PIcon name="sliders" size={16} />
            <span className="tx-filters-word" aria-hidden="true">Filters{extra ? ` · ${extra}` : ''}</span>
            {extra > 0 && <span className="tx-filters-count" aria-hidden="true">{extra}</span>}
          </button>
          <button type="button" className="pk-filter tx-add" onClick={() => setAdding(true)}
                  aria-label="Add a transaction">
            <PIcon name="plus" size={16} /><span className="tx-add-word" aria-hidden="true">Add</span>
          </button>
          {filters.merchant && (
            <button type="button" className="pk-filter active tx-toggle" aria-pressed="true"
                    onClick={() => choose({ merchant: '' })}>
              {filters.merchant} <PIcon name="x" size={14} />
            </button>
          )}
          {filters.day && (
            <button type="button" className="pk-filter active tx-toggle" aria-pressed="true"
                    onClick={() => choose({ day: '' })}>
              {shortDate(filters.day)} <PIcon name="x" size={14} />
            </button>
          )}
          {filters.first && filters.last && (
            <button type="button" className="pk-filter active tx-toggle" aria-pressed="true"
                    onClick={() => choose({ first: '', last: '' })}>
              {rangeWords(filters.first, filters.last)} <PIcon name="x" size={14} />
            </button>
          )}
          {filters.owed && (
            <button type="button" className="pk-filter active tx-toggle" aria-pressed="true"
                    onClick={() => choose({ owed: '' })}>
              Owed to you <PIcon name="x" size={14} />
            </button>
          )}
          {filtered && !empty && (
            <PButton variant="text" className="tx-clear" onClick={clearFilters}>
              Clear filters
            </PButton>
          )}
        </div>
      </div>

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
          {reviewCount > 0 && !filters.look && (
            <Alert action="Review" onAction={() => onTab?.('review')}>
              {dupes > 0 ? duplicateAlert(dupes) : (
                <>
                  <span className="tx-look-long">
                    {reviewCount === 1 ? '1 transaction needs a quick look.'
                      : `${reviewCount} transactions need a quick look.`} It takes about a minute.
                  </span>
                  <span className="tx-look-short">
                    {reviewCount === 1 ? '1 needs a quick look.' : `${reviewCount} need a quick look.`}
                  </span>
                </>
              )}
            </Alert>
          )}

          {shownRows.length > 0 && (
            <section className={`pk-list${desktop ? ' tx-keys' : ''}${selectable ? ' tx-selectable' : ''}`}
                     aria-label="Transactions"
                     ref={listRef} onKeyDown={onListKey}
                     aria-describedby={desktop ? 'tx-keys-help' : undefined}>
              {desktop && (
                <p className="pk-sr" id="tx-keys-help">
                  {singleKey ? 'Use the arrow keys or J and K to move, X to select, Y to confirm, '
                    + 'C to change the category, U for a one-off and question mark for every shortcut.'
                    : 'Use the arrow keys to move and Shift with the arrow keys to select.'}
                </p>
              )}
              {sections.map((d) => {
                const p = dayParts(d.key);
                const spent = data?.day_spent?.[d.key] ?? 0;
                return (
                  <div key={d.key} role="group" aria-label={d.label}>
                    <div className="tx-day">
                      <span className="tx-day-name">{p.name}</span>
                      <span className="tx-day-date">{p.date}</span>
                      {spent >= 0.005 && (
                        <span className="tx-day-total">{txAmount(spent, { signed: true })}</span>
                      )}
                    </div>
                    {d.rows.map(rowFor)}
                  </div>
                );
              })}
              {more > 0 && (
                <div className="tx-more">
                  <button type="button" className="tx-earlier" disabled={loadingMore} onClick={showMore}>
                    Show earlier
                  </button>
                </div>
              )}
            </section>
          )}

          {desktop && shownRows.length > 0 && (
            <PButton variant="text" className="tx-keys-link" onClick={() => setHelp(true)}
                     aria-keyshortcuts={singleKey ? '?' : undefined}>
              Keyboard shortcuts
            </PButton>
          )}
        </>
      )}

      {anySelected && (
        <SelectedBar count={selected.length} total={selectedTotal} singleKey={desktop && singleKey}
                     onChange={() => setPicking(selected)}
                     onMark={() => setMarking(selected)}
                     onTag={() => setTagging(selected)}
                     onLeaveOut={() => leaveOut(selected)}
                     onConfirm={() => confirmRows(selected)}
                     onClear={clearSelection} />
      )}

      {openId && (
        <TransactionDetail id={openId} initial={shownRows.find((r) => r.id === openId)}
                           categories={categories} onClose={close} onSaved={saved}
                           startStep={openStep} />
      )}
      {adding && (
        <AddTransaction categories={categories.filter((c) => !c.hidden)} onClose={() => setAdding(false)}
                        onSaved={() => { setAdding(false); saved(); }} />
      )}
      {filtering && (
        <TxFiltersPanel filters={{ ...filters, cat: categoryValue }} thisMonth={thisMonth()}
                        categoryOptions={categoryOptions}
                        accounts={accountOptions.flatMap((o) => o.options ?? [o]).filter((o) => o.value)}
                        tags={data?.tag_totals ?? (data?.tags ?? [])}
                        onApply={({ cat, ...f }) => { setFiltering(false); choose(f); }}
                        onClose={() => setFiltering(false)} />
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
