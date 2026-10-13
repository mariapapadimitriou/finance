// The transactions screen keeps its place in the address bar, so a filtered
// list (/transactions?month=2026-10&group=lifestyle) can be linked to from
// anywhere — Home, an alert, an explanation sheet — and back/forward work.
// Growth's Path and Insights have addresses too; everything else lives at "/".

export const TX_KEYS = ['month', 'account', 'group', 'category', 'excluded', 'joint', 'recurring', 'q'];

// Needs a look (R-01, THL-123) has an address under the list's.
export const REVIEW_PATH = '/transactions/review';

// The Path page (THL-129 GR-01) has an address too, so Home can link to it.
export const PATH_PATH = '/growth';

/** True at /growth. */
export function isPathUrl(loc = window.location) {
  return /^\/growth\/?$/.test(loc.pathname);
}

/** Point the address bar at the Path page. */
export function writePathUrl({ push = true } = {}) {
  if (isPathUrl()) return;
  window.history[push ? 'pushState' : 'replaceState'](null, '', PATH_PATH);
}

// Growth › Insights (THL-186, THL-196 GR-28) and its detail views (GR-25 to
// GR-27, GR-29 to GR-32), so a detail can be linked to and Back works:
// /growth/insights/<view>?month=2026-09&category=Dining.
export const INSIGHTS_PATH = '/growth/insights';
export const INSIGHTS_VIEWS = ['month', 'category', 'subscriptions', 'trend', 'where', 'money',
                               'savings'];
const INSIGHTS_EVENT = 'pearl:insights';

/** {view, month, category} at /growth/insights…, or null anywhere else. */
export function readInsightsUrl(loc = window.location) {
  const m = loc.pathname.match(/^\/growth\/insights(?:\/([a-z]+))?\/?$/);
  if (!m) return null;
  const params = new URLSearchParams(loc.search);
  const view = INSIGHTS_VIEWS.includes(m[1]) ? m[1] : '';
  const month = /^\d{4}-\d{2}$/.test(params.get('month') ?? '') ? params.get('month') : '';
  return { view, month, category: view === 'category' ? params.get('category') ?? '' : '' };
}

export const isInsightsUrl = (loc = window.location) => readInsightsUrl(loc) !== null;

export function insightsHref({ view = '', month = '', category = '' } = {}) {
  const params = new URLSearchParams();
  if (month) params.set('month', month);
  if (view === 'category' && category) params.set('category', category);
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

// Where Goals should open when another page sends her there (THL-12 R3: a
// recommendation's "Try it" or "Move to savings"). Kept for the one visit;
// Goals takes it on arrival. Storage can be blocked, so it's only a nicety.
const GOALS_INTENT = 'pearl.goalsIntent';

export function setGoalsIntent(intent) {
  try { window.sessionStorage.setItem(GOALS_INTENT, JSON.stringify(intent)); } catch { /* blocked */ }
}

export function takeGoalsIntent() {
  try {
    const raw = window.sessionStorage.getItem(GOALS_INTENT);
    window.sessionStorage.removeItem(GOALS_INTENT);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
