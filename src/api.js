// API client and shared formatting helpers.

export const API = import.meta.env?.VITE_API || 'http://localhost:5050';

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

export const importFiles   = (files) => json('POST', '/api/import', { files });
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
