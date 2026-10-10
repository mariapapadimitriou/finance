// The transactions screen keeps its place in the address bar, so a filtered
// list (/transactions?month=2026-10&group=lifestyle) can be linked to from
// anywhere — Home, an alert, an explanation sheet — and back/forward work.
// The rest of the app has no addresses yet: everything else lives at "/".

export const TX_KEYS = ['month', 'account', 'group', 'category', 'q'];

/** {path, id, filters} for the current address, or null when it is not the list. */
export function readTxUrl(loc = window.location) {
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
