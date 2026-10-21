// The transactions screen keeps its place in the address bar, so a filtered
// list (/transactions?month=2026-10&group=lifestyle) can be linked to from
// anywhere — Home, an alert, an explanation sheet — and back/forward work.
// Wins' Path, Cash flow's Insights, and Save with its projection, calculator
// and Learn (THL-248) have addresses too; everything else lives at "/". The
// old /growth/… addresses redirect to their new homes (`redirectOldUrl`).

export const TX_KEYS = ['month', 'account', 'group', 'category', 'excluded', 'joint', 'recurring', 'q', 'day',
  // What was this? (2026-10-14): a tag, what counts, an amount range, pending
  // only, needs a look only, one merchant, and the view (by day, merchant or
  // category).
  'tag', 'counts', 'amount', 'pending', 'look', 'merchant', 'by', 'owed',
  // Select days on the calendar (CAL-06, 2026-10-16): the list for a range of days.
  'first', 'last'];

// Needs a look (R-01, THL-123) has an address under the list's.
export const REVIEW_PATH = '/transactions/review';

// Cash flow › Calendar (THL-245 CAL-01, THL-255) at /cash-flow/calendar, a
// month behind it: /cash-flow/calendar?month=2026-09.
export const CALENDAR_PATH = '/cash-flow/calendar';
const CALENDAR_EVENT = 'pearl:calendar';

/** {month} at /cash-flow/calendar…, or null anywhere else. */
export function readCalendarUrl(loc = window.location) {
  if (!/^\/cash-flow\/calendar\/?$/.test(loc.pathname)) return null;
  const month = new URLSearchParams(loc.search).get('month') ?? '';
  return { month: /^\d{4}-\d{2}$/.test(month) ? month : '' };
}

export const isCalendarUrl = (loc = window.location) => readCalendarUrl(loc) !== null;

export const calendarHref = ({ month = '' } = {}) => `${CALENDAR_PATH}${month ? `?month=${month}` : ''}`;

/** Point the address bar at the calendar, or one of its months. */
export function writeCalendarUrl(state = {}, { push = true } = {}) {
  const href = calendarHref(state);
  if (href === window.location.pathname + window.location.search) return;
  window.history[push ? 'pushState' : 'replaceState'](null, '', href);
  window.dispatchEvent(new Event(CALENDAR_EVENT));
}

/** Call `fn` when the calendar's address changes, from either direction. */
export function onCalendarUrl(fn) {
  window.addEventListener('popstate', fn);
  window.addEventListener(CALENDAR_EVENT, fn);
  return () => {
    window.removeEventListener('popstate', fn);
    window.removeEventListener(CALENDAR_EVENT, fn);
  };
}

// Growth › Insights (THL-186, THL-196 GR-28) and its detail views (GR-25 to
// GR-27, GR-29 to GR-32), so a detail can be linked to and Back works:
// /growth/insights/<view>?month=2026-09&category=Dining.
export const INSIGHTS_PATH = '/cashflow/insights';
export const INSIGHTS_VIEWS = ['month', 'category', 'subscriptions', 'trend', 'where', 'money',
                               'savings'];
const INSIGHTS_EVENT = 'pearl:insights';

/** {view, month, category} at /growth/insights…, or null anywhere else. */
export function readInsightsUrl(loc = window.location) {
  const m = loc.pathname.match(/^\/cashflow\/insights(?:\/([a-z]+))?\/?$/);
  if (!m) return null;
  const params = new URLSearchParams(loc.search);
  const view = INSIGHTS_VIEWS.includes(m[1]) ? m[1] : '';
  const month = /^\d{4}-\d{2}$/.test(params.get('month') ?? '') ? params.get('month') : '';
  const span = ['3', '6', '12'].includes(params.get('span') ?? '') ? params.get('span') : '';
  const show = ['essentials', 'lifestyle', 'fixed', 'variable'].includes(params.get('show') ?? '')
    ? params.get('show') : '';
  return { view, month, category: view === 'category' ? params.get('category') ?? '' : '',
           account: params.get('account') ?? '', span, one_offs: params.get('one_offs') === 'out' ? 'out' : '',
           show };
}

export const isInsightsUrl = (loc = window.location) => readInsightsUrl(loc) !== null;

export function insightsHref({ view = '', month = '', category = '', account = '', span = '',
                               one_offs = '', show = '' } = {}) {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (view === 'category' && category) params.set('category', category);
  if (account) params.set('account', account);
  if (span) params.set('span', span);
  if (one_offs) params.set('one_offs', one_offs);
  if (show) params.set('show', show);
  const qs = params.toString();
  return `${INSIGHTS_PATH}${view ? `/${view}` : ''}${qs ? `?${qs}` : ''}`;
}

/** Point the address bar at Insights or one of its views, and tell the page. */
export function writeInsightsUrl(state = {}, { push = true } = {}) {
  const href = insightsHref(state);
  if (href !== window.location.pathname + window.location.search) {
    window.history[push ? 'pushState' : 'replaceState'](null, '', href);
  }
  window.dispatchEvent(new Event(INSIGHTS_EVENT));
}

/** Calls `fn` whenever the Insights address changes, by Back or by a link. */
export function onInsightsUrl(fn) {
  window.addEventListener('popstate', fn);
  window.addEventListener(INSIGHTS_EVENT, fn);
  return () => {
    window.removeEventListener('popstate', fn);
    window.removeEventListener(INSIGHTS_EVENT, fn);
  };
}

// Save › Projections (THL-197 GR-33, THL-248) and its detail views — GR-34
// this month, GR-35 the next 30 days, GR-36 savings in a year — at
// Old addresses land where their pages went, so a saved link or bookmark
// never 404s. Save, Wins and the old Growth group are gone (2026-10-21):
// their addresses land on Home, except Growth › Insights, which moved to
// Cash flow.
const OLD_GROWTH = [
  [/^\/growth\/insights(\/[a-z]+)?$/, (m) => `/cashflow/insights${m[1] ?? ''}`],
  [/^\/(growth|wins|save|goals)(\/.*)?$/, () => '/'],
  // The calendar's address is spelled cash-flow (THL-245); the one-word
  // spelling Insights uses lands there too.
  [/^\/cashflow\/calendar$/, () => CALENDAR_PATH],
];

/** The new address for an old one, or null when it isn't old. */
export function newUrlFor(pathname) {
  const path = pathname.replace(/\/+$/, '') || '/';
  for (const [re, to] of OLD_GROWTH) {
    const m = path.match(re);
    if (m) return to(m);
  }
  return null;
}

/** Replace an old Growth address with its new one before the app reads it. */
export function redirectOldUrl(loc = window.location) {
  const to = newUrlFor(loc.pathname);
  if (to) window.history.replaceState(null, '', `${to}${loc.search}`);
  return to;
}

/** True at /transactions/review. */
export function isReviewUrl(loc = window.location) {
  return /^\/transactions\/review\/?$/.test(loc.pathname);
}

/** Point the address bar at Needs a look. */
export function writeReviewUrl({ push = true } = {}) {
  if (isReviewUrl()) return;
  window.history[push ? 'pushState' : 'replaceState'](null, '', REVIEW_PATH);
}

/** {path, id, filters} for the current address, or null when it is not the list. */
export function readTxUrl(loc = window.location) {
  if (isReviewUrl(loc)) return null;
  const m = loc.pathname.match(/^\/transactions(?:\/([^/]+))?\/?$/);
  if (!m) return null;
  const params = new URLSearchParams(loc.search);
  const filters = {};
  TX_KEYS.forEach((k) => {
    const v = params.get(k);
    if (v) filters[k] = v;
  });
  return { id: m[1] ? decodeURIComponent(m[1]) : null, filters, from: params.get('from') || '' };
}

export function txHref({ id = null, filters = {}, from = '' } = {}) {
  const params = new URLSearchParams();
  TX_KEYS.forEach((k) => { if (filters[k]) params.set(k, filters[k]); });
  if (from) params.set('from', from);
  const qs = params.toString();
  return `/transactions${id ? `/${encodeURIComponent(id)}` : ''}${qs ? `?${qs}` : ''}`;
}

/** Point the address bar at the list; push adds a history entry, replace doesn't. */
export function writeTxUrl(state, { push = false } = {}) {
  const href = txHref(state);
  if (href === window.location.pathname + window.location.search) return;
  window.history[push ? 'pushState' : 'replaceState'](null, '', href);
}

/** Leave the list's address when the app goes elsewhere. */
export function clearUrl() {
  if (window.location.pathname !== '/' && !window.location.search.includes('reset=')) {
    window.history.pushState(null, '', '/');
  }
}
