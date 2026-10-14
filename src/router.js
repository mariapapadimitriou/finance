// The transactions screen keeps its place in the address bar, so a filtered
// list (/transactions?month=2026-10&group=lifestyle) can be linked to from
// anywhere — Home, an alert, an explanation sheet — and back/forward work.
// Growth's Path, Insights, Projections and Learn have addresses too;
// everything else lives at "/".

export const TX_KEYS = ['month', 'account', 'group', 'category', 'excluded', 'joint', 'recurring', 'q',
  // What was this? (2026-10-14): a tag, what counts, an amount range, pending
  // only, needs a look only, one merchant, and the view (by day, merchant or
  // category).
  'tag', 'counts', 'amount', 'pending', 'look', 'merchant', 'by'];

// Needs a look (R-01, THL-123) has an address under the list's.
export const REVIEW_PATH = '/transactions/review';

// The Path page (THL-129 GR-01) has an address too, so Home can link to it,
// and each step's own screen (GR-02 to GR-04) one beneath it:
// /growth/path/<step>.
export const PATH_PATH = '/growth';
export const PATH_STEPS = ['income', 'bills', 'essentials', 'first_stop', 'full', 'saved_more',
                           'cards', 'invest'];
const PATH_EVENT = 'pearl:path';

/** {step} at /growth or /growth/path/<step>, or null anywhere else. */
export function readPathUrl(loc = window.location) {
  const path = loc.pathname.replace(/\/+$/, '') || '/';
  if (path === PATH_PATH) return { step: '' };
  const m = path.match(/^\/growth\/path\/([a-z_]+)$/);
  return m && PATH_STEPS.includes(m[1]) ? { step: m[1] } : null;
}

/** True at /growth and at a step's own screen. */
export const isPathUrl = (loc = window.location) => readPathUrl(loc) !== null;

export const pathHref = (step = '') => (step ? `${PATH_PATH}/path/${step}` : PATH_PATH);

/** Point the address bar at the Path page or one of its steps, and tell the page. */
export function writePathUrl({ step = '', push = true } = {}) {
  const href = pathHref(step);
  if (href !== window.location.pathname) {
    window.history[push ? 'pushState' : 'replaceState'](null, '', href);
  }
  window.dispatchEvent(new Event(PATH_EVENT));
}

/** Calls `fn` whenever the Path address changes, by Back or by a link. */
export function onPathUrl(fn) {
  window.addEventListener('popstate', fn);
  window.addEventListener(PATH_EVENT, fn);
  return () => {
    window.removeEventListener('popstate', fn);
    window.removeEventListener(PATH_EVENT, fn);
  };
}

// Growth › Learn (THL-134 GR-11, at /growth/learn) and a module (GR-12 to
// GR-14) at /growth/learn/<module>. ?from=ready means she came from the
// readiness checklist (GR-16), so the done state offers the way back. The
// safe-to-spend explainer is a page of its own there too.
export const LEARN_PATH = '/growth/learn';
const LEARN_EVENT = 'pearl:learn';

/** {module, from} at /growth/learn…, or null anywhere else. */
export function readLearnUrl(loc = window.location) {
  const m = loc.pathname.match(/^\/growth\/learn(?:\/([a-z-]+))?\/?$/);
  if (!m) return null;
  const from = new URLSearchParams(loc.search).get('from') === 'ready' ? 'ready' : '';
  return { module: m[1] ?? '', from };
}

export const isLearnUrl = (loc = window.location) => readLearnUrl(loc) !== null;

export function learnHref({ module = '', from = '' } = {}) {
  return `${LEARN_PATH}${module ? `/${module}` : ''}${module && from ? `?from=${from}` : ''}`;
}

/** Point the address bar at Learn or one of its modules, and tell the page. */
export function writeLearnUrl(state = {}, { push = true } = {}) {
  const href = learnHref(state);
  if (href !== window.location.pathname + window.location.search) {
    window.history[push ? 'pushState' : 'replaceState'](null, '', href);
  }
  window.dispatchEvent(new Event(LEARN_EVENT));
}

/** Calls `fn` whenever the Learn address changes, by Back or by a link. */
export function onLearnUrl(fn) {
  window.addEventListener('popstate', fn);
  window.addEventListener(LEARN_EVENT, fn);
  return () => {
    window.removeEventListener('popstate', fn);
    window.removeEventListener(LEARN_EVENT, fn);
  };
}

/** True when the partner sent her back (THL-136 GR-20): ?from=partner. */
export const fromPartner = (loc = window.location) =>
  new URLSearchParams(loc.search).get('from') === 'partner';

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

// Growth › Projections (THL-197 GR-33) and its detail views — GR-34 this
// month, GR-35 the next 30 days, GR-36 savings in a year, GR-17 and GR-18
// the growth calculator on its own — at /growth/projections/<view>. Unveil's
// screens live beside them, reached from the Path: GR-16 Ready to invest at
// /growth/ready, GR-37 "Opened an investing account?" at /growth/unveil and
// GR-10, Unveil done, at /growth/unveil/done.
export const PROJECTIONS_PATH = '/growth/projections';
export const PROJECTIONS_VIEWS = ['forecast', 'next30', 'savings', 'calculator'];
const UNVEIL_PATHS = { ready: '/growth/ready', unveil: '/growth/unveil', done: '/growth/unveil/done' };
const PROJECTIONS_EVENT = 'pearl:projections';

/** {view} at /growth/projections…, /growth/ready or /growth/unveil…, or null. */
export function readProjectionsUrl(loc = window.location) {
  const path = loc.pathname.replace(/\/+$/, '');
  const unveil = Object.entries(UNVEIL_PATHS).find(([, p]) => p === path);
  if (unveil) return { view: unveil[0] };
  const m = path.match(/^\/growth\/projections(?:\/([a-z0-9]+))?$/);
  if (!m) return null;
  return { view: PROJECTIONS_VIEWS.includes(m[1]) ? m[1] : '' };
}

export const isProjectionsUrl = (loc = window.location) => readProjectionsUrl(loc) !== null;

export function projectionsHref(view = '') {
  return UNVEIL_PATHS[view] ?? `${PROJECTIONS_PATH}${view ? `/${view}` : ''}`;
}

/** Point the address bar at Projections, one of its views or an Unveil screen. */
export function writeProjectionsUrl(view = '', { push = true } = {}) {
  const href = projectionsHref(view);
  if (href !== window.location.pathname) {
    window.history[push ? 'pushState' : 'replaceState'](null, '', href);
  }
  window.dispatchEvent(new Event(PROJECTIONS_EVENT));
}

/** Calls `fn` whenever the Projections address changes, by Back or by a link. */
export function onProjectionsUrl(fn) {
  window.addEventListener('popstate', fn);
  window.addEventListener(PROJECTIONS_EVENT, fn);
  return () => {
    window.removeEventListener('popstate', fn);
    window.removeEventListener(PROJECTIONS_EVENT, fn);
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
