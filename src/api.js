// API client and shared formatting helpers.

// In dev the UI runs on Vite's server and the API on its own port. In a built
// deployment both are served from one origin, so requests go to a relative
// path and no host needs hard-coding. VITE_API overrides either way.
export const API = import.meta.env?.VITE_API
  ?? (import.meta.env?.DEV ? 'http://localhost:5050' : '');

async function req(path, options = {}) {
  const r = await fetch(`${API}${path}`, options);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}

const json = (method, path, payload) =>
  req(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

export const getSummary      = () => req('/api/summary');
export const getInsights     = () => req('/api/insights');
export const getRecurring    = () => req('/api/recurring');
export const getAccounts     = () => req('/api/accounts');
export const getCategories   = () => req('/api/categories');
export const getSources      = () => req('/api/sources');
export const getImports      = () => req('/api/imports');
export const getTrips        = () => req('/api/trips');
export const addTrip         = (trip) => json('POST', '/api/trips', trip);
export const updateTrip      = (id, trip) => json('PATCH', `/api/trips/${id}`, trip);
export const deleteTrip      = (id) => req(`/api/trips/${id}`, { method: 'DELETE' });

export const getPlan         = (month) =>
  req(`/api/plan${month ? `?month=${month}` : ''}`);
export const setPlanAmount   = (amount) =>
  json('PUT', '/api/plan', { monthly_amount: amount });
export const simulateSpend   = (amount, month) =>
  json('POST', `/api/plan/simulate${month ? `?month=${month}` : ''}`, { amount });
export const setBucket       = (name, balance) =>
  json('PUT', '/api/buckets', { name, balance });
export const deleteBucket    = (id) => req(`/api/buckets/${id}`, { method: 'DELETE' });
export const coverFromBucket = (id, amount, month) =>
  json('POST', `/api/buckets/${id}/cover`, { amount, month });

export const getProgress     = (month) =>
  req(`/api/progress${month ? `?month=${month}` : ''}`);

export const getProjections  = (target) =>
  req(`/api/projections${target ? `?target=${target}` : ''}`);
export const setIncome       = (income) =>
  json('PUT', '/api/projections/income', { monthly_income: income });

/**
 * Add a transaction by hand.
 *
 * A 409 is not a failure here — it is the duplicate check reporting what it
 * found, so the body travels with the thrown error for the form to show.
 */
export async function addTransaction(entry) {
  const r = await fetch(`${API}/api/transactions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  const body = await r.json().catch(() => ({}));
  if (r.status === 409) return { conflict: true, ...body };
  if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return { conflict: false, ...body };
}

export const deleteTransaction = (id) =>
  req(`/api/transactions/${id}`, { method: 'DELETE' });

export const getBudgets      = (month) =>
  req(`/api/budgets${month ? `?month=${month}` : ''}`);

export const getBreakdown = (month, days = 90) =>
  req(`/api/breakdown?${new URLSearchParams({ ...(month ? { month } : {}), days })}`);

export function getTransactions(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) params.set(k, v);
  });
  return req(`/api/transactions?${params}`);
}

export const importFiles = (payload) =>
  // FormData carries binary PDFs correctly; the browser sets the boundary
  // header itself, so we must not set Content-Type here.
  (payload instanceof FormData
    ? req('/api/import', { method: 'POST', body: payload })
    : json('POST', '/api/import', { files: payload }));
export const setBudgets    = (budgets) => json('PUT', '/api/budgets', { budgets });
export const setCategory   = (id, category, applyToMerchant = false) =>
  json('PATCH', `/api/transactions/${id}`, {
    category, apply_to_merchant: applyToMerchant,
  });

export const dismissFinding = (id) => req(`/api/insights/${id}/dismiss`, { method: 'POST' });
export const restoreFinding = (id) => req(`/api/insights/${id}/dismiss`, { method: 'DELETE' });
export const runNarrative   = () => req('/api/narrative', { method: 'POST' });
export const clearLedger    = (account) =>
  req(`/api/transactions${account ? `?account=${encodeURIComponent(account)}` : ''}`,
      { method: 'DELETE' });

// ── Formatting ───────────────────────────────────────────────────────────────

export function money(n, { cents = false, sign = false } = {}) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  const text = abs.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  });
  if (n < 0) return `−${text}`;
  return sign ? `+${text}` : text;
}

export function pct(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function monthLabel(month, { long = false } = {}) {
  if (!month) return '—';
  const [y, m] = month.split('-').map(Number);
  const name = MONTH_NAMES[m - 1] ?? month;
  return long ? `${name} ${y}` : `${name} '${String(y).slice(2)}`;
}

export function dateLabel(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-').map(Number);
  return `${MONTH_NAMES[m - 1]} ${d}`;
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
