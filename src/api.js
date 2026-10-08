// API client and shared formatting helpers.

// In dev the UI runs on Vite's server and the API on its own port. In a built
// deployment both are served from one origin, so requests go to a relative
// path and no host needs hard-coding. VITE_API overrides either way.
export const API = import.meta.env?.VITE_API
  ?? (import.meta.env?.DEV ? 'http://localhost:5050' : '');

// Anything that needs the session cookie has to send it, and in dev the UI is
// on a different origin from the API, where cookies are not sent by default.
const CREDENTIALS = { credentials: 'include' };

/** Notified when the server says the session is gone, so the app can show the
 *  login screen instead of a wall of failed panels. */
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function req(path, options = {}) {
  const r = await fetch(`${API}${path}`, { ...CREDENTIALS, ...options });
  const body = await r.json().catch(() => ({}));
  if (r.status === 401 && body.unauthorized) {
    onUnauthorized();
    throw new Error('Signed out.');
  }
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

/**
 * What to call an account so you can tell which it is: the bank, the kind of
 * account and its last four digits — "TD Bank · Chequing ••1234". Falls back
 * to the name the bank or the statement gave it when the bank isn't known.
 */
export function accountTitle(a) {
  if (!a) return '';
  if (!a.institution) return a.account_name || a.account_id;
  return `${a.institution} · ${a.kind_label}${a.mask ? ` ••${a.mask}` : ''}`;
}
// Removing a connected account has to stop it syncing too, or the next sync
// fetches the whole thing again. `stopSyncing: false` deletes the rows only.
export const deleteAccount   = (id, stopSyncing = true) =>
  req(`/api/accounts/${encodeURIComponent(id)}`
      + (stopSyncing ? '' : '?stop_syncing=0'), { method: 'DELETE' });
export const setAccountSync  = (id, enabled) =>
  json('PUT', `/api/accounts/${encodeURIComponent(id)}/sync`, { enabled });
export const getDuplicateAudit = () => req('/api/audit/duplicates');
export const resetLedger     = (keepBanks) =>
  json('POST', '/api/reset', { confirm: 'erase', keep_banks: keepBanks });
export const getCategories   = () => req('/api/categories');
export const getSources      = () => req('/api/sources');

// ── Signing in ───────────────────────────────────────────────────────────────
export const getAuthStatus   = () => req('/api/auth/status');
export const logout          = () => json('POST', '/api/auth/logout', {});

/** Kept out of `req` so a wrong password reads as an answer, not a crash. */
async function authPost(path, payload) {
  const r = await fetch(`${API}${path}`, {
    ...CREDENTIALS,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await r.json().catch(() => ({}));
  return { ok: r.ok, ...body };
}
export const login          = (username, password) =>
  authPost('/api/auth/login', { username, password });
export const changePassword = (current, next) =>
  authPost('/api/auth/password', { current, new: next });
export const signupWithEmail = (username, email, password) =>
  authPost('/api/auth/signup', { username, email, password });
export const forgotPassword = (identifier) =>
  authPost('/api/auth/forgot', { identifier });
export const resetPassword  = (token, password) =>
  authPost('/api/auth/reset', { token, password });
export const changeEmail    = (email) => authPost('/api/auth/email', { email });


// ── Plaid ────────────────────────────────────────────────────────────────────
export const getPlaidItems   = () => req('/api/plaid/items');
export const createLinkToken = () => json('POST', '/api/plaid/link-token', {});
export const checkPlaidKeys  = () => json('POST', '/api/plaid/check', {});
export const exchangePublicToken = (publicToken, institution) =>
  json('POST', '/api/plaid/exchange',
       { public_token: publicToken, institution });
export const syncPlaid       = () => json('POST', '/api/plaid/sync', {});
export const unlinkBank      = (id) =>
  req(`/api/plaid/items/${id}`, { method: 'DELETE' });
export const getHealth       = () => req('/api/health');
export const getImports      = () => req('/api/imports');
export const getTrips        = () => req('/api/trips');
export const addTrip         = (trip) => json('POST', '/api/trips', trip);
export const getTripSuggestions = () => req('/api/trips/suggestions');
export const updateTrip      = (id, trip) => json('PATCH', `/api/trips/${id}`, trip);
export const deleteTrip      = (id) => req(`/api/trips/${id}`, { method: 'DELETE' });

// One past week as it finished — the arrows on the Allowance card.
export const getWeek         = (on) => req(`/api/plan/week?on=${encodeURIComponent(on)}`);
export const getPlan         = (month) =>
  req(`/api/plan${month ? `?month=${month}` : ''}`);
export const simulateSpend   = (amount, month) =>
  json('POST', `/api/plan/simulate${month ? `?month=${month}` : ''}`, { amount });

// Piggy banks: annual costs collected monthly, and spending charged to them
// instead of to the month it fell in.
export const getBanks        = () => req('/api/piggy');
export const addBank         = (bank) => json('POST', '/api/piggy', bank);
export const updateBank      = (id, bank) => json('PATCH', `/api/piggy/${id}`, bank);
export const deleteBank      = (id) => req(`/api/piggy/${id}`, { method: 'DELETE' });
export const allocateToBank  = (id, txnId) =>
  json('POST', `/api/piggy/${id}/allocate`, { txn_id: txnId });
export const unallocate      = (txnId) =>
  req(`/api/piggy/allocations/${txnId}`, { method: 'DELETE' });
// Put back money a bank lent the month. Nothing creates these any more.
export const undoDraw        = (id) => req(`/api/piggy/draws/${id}`, { method: 'DELETE' });

// The mortgage: saved terms, whose monthly cost is the Mortgage commitment.
export const getMortgage     = () => req('/api/mortgage');
export const previewMortgage = (terms) => json('POST', '/api/mortgage/preview', terms);
export const saveMortgage    = (terms) => json('PUT', '/api/mortgage', terms);
export const deleteMortgage  = () => req('/api/mortgage', { method: 'DELETE' });
export const compareMortgage = (terms, options) =>
  json('POST', '/api/mortgage/compare', { ...terms, ...options });


// The money plan: income in, commitments and savings out, the rest budgeted.
export const getPlanSetup    = () => req('/api/plan/setup');
export const savePlanSetup   = (income, savings) =>
  json('PUT', '/api/plan/setup', { income, savings });
// The savings figure on its own. The endpoint writes only the fields it is
// given, and the slider has no business sending an income it never showed.
export const saveSavings     = (savings) =>
  json('PUT', '/api/plan/setup', { savings });
export const applyPlanBudgets = () => json('POST', '/api/plan/setup/apply', {});
// Your own split of the monthly total: the lines you focus on, and every
// amount. The server refuses one that does not add up to the total.
export const setAllocation   = (focus, budgets) =>
  json('PUT', '/api/budgets/allocation', { focus, budgets });
export const addFixedCost    = (cost) => json('POST', '/api/plan/fixed', cost);
export const deleteFixedCost = (id) =>
  req(`/api/plan/fixed/${id}`, { method: 'DELETE' });


/**
 * `savings` previews a different savings figure without saving it, so the
 * slider on the tab moves the real arithmetic rather than a copy of it.
 */
// Which categories share a budget line. Budgeting only — see finance/groups.py.
export const getCategoryGroups = () => req('/api/category-groups');
export const setCategoryGroups = (groups) =>
  json('PUT', '/api/category-groups', { groups });

export const getProjections  = (target, savings) => {
  const q = new URLSearchParams();
  if (target) q.set('target', target);
  if (savings !== undefined && savings !== null) q.set('savings', savings);
  const s = q.toString();
  return req(`/api/projections${s ? `?${s}` : ''}`);
};

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

// Statements shipped with the app for a card that cannot be connected. Safe to
// call twice: the server runs them through the same de-duplication as an upload.
export const getBundled    = () => req('/api/import/bundled');
export const importBundled = (key) =>
  json('POST', '/api/import/bundled', { key });

export const importFiles = (payload) =>
  // FormData carries binary PDFs correctly; the browser sets the boundary
  // header itself, so we must not set Content-Type here.
  (payload instanceof FormData
    ? req('/api/import', { method: 'POST', body: payload })
    : json('POST', '/api/import', { files: payload }));
export const setBudgets    = (budgets) => json('PUT', '/api/budgets', { budgets });
// How much of a charge was yours, when friends paid you back the rest.
// null puts the whole charge back.
export const setShare      = (id, myShare) =>
  json('PUT', `/api/transactions/${id}/share`, { my_share: myShare });
// Money that left a bank account for somewhere Spendie can't see, waiting to
// be called spent or saved.
export const getUnsorted   = () => req('/api/transfers/unsorted');
// Say where a group of transfers went; `remember` makes it the rule for
// those names.
export const sortTransfers = (ids, category, remember) =>
  json('POST', '/api/transfers/sort', { ids, category, remember });
// What counts as saved lately, to check and undo.
export const getSaved      = (months = 2) => req(`/api/transfers/saved?months=${months}`);
// Undo where you said something went.
export const unsortTransaction = (id) => json('POST', `/api/transactions/${id}/unsort`, {});
// Money friends sent back for a charge: what is linked, and what might be.
export const getPaybacks   = (id) => req(`/api/transactions/${id}/paybacks`);
export const linkPayback   = (id, inflowId) =>
  json('POST', `/api/transactions/${id}/paybacks/${inflowId}`, {});
export const unlinkPayback = (id, inflowId) =>
  req(`/api/transactions/${id}/paybacks/${inflowId}`, { method: 'DELETE' });
// How much of a transaction was put away (saved). null clears it.
export const setInvested   = (id, amount) =>
  json('PUT', `/api/transactions/${id}/invested`, { amount });
export const setCategory   = (id, category, applyToMerchant = false) =>
  json('PATCH', `/api/transactions/${id}`, {
    category, apply_to_merchant: applyToMerchant,
  });

// Where the ledger starts, and re-running categorization over what is already
// in it. Both exist for the same reason: a rule that improved after the rows
// were imported does not reach them until something asks it to.
export const getLedgerStart  = () => req('/api/ledger/start');
export const setLedgerStart  = (start, trim) =>
  json('PUT', '/api/ledger/start', { start, trim });
export const recategorizeAll = () => json('POST', '/api/recategorize', {});

export const dismissFinding = (id) => req(`/api/insights/${id}/dismiss`, { method: 'POST' });
export const restoreFinding = (id) => req(`/api/insights/${id}/dismiss`, { method: 'DELETE' });

// ── Formatting ───────────────────────────────────────────────────────────────

/**
 * What this ledger is denominated in.
 *
 * Every amount is stored in the currency the card was billed in — Plaid
 * reports it per transaction and the CSV layouts record it — but this
 * formatter used to say USD regardless, so a Canadian ledger read as
 * American on every page. The data was never wrong; the label was.
 *
 * Set once from the summary, before any figure is drawn. Blank until then
 * rather than guessed, because guessing is what produced the bug.
 */
let LEDGER_CURRENCY = '';
export const setLedgerCurrency = (code) => { LEDGER_CURRENCY = code || ''; };

export function money(n, { cents = false, sign = false, currency } = {}) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  const code = currency || LEDGER_CURRENCY;
  const opts = {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  };
  // narrowSymbol keeps CAD as "$" rather than "CA$". Correct for a ledger
  // that is entirely one currency, which is the normal case; a mixed one is
  // reported as mixed on the Accounts tab rather than papered over here.
  let text;
  try {
    text = abs.toLocaleString(undefined, {
      ...opts, style: 'currency', currency: code || 'USD',
      currencyDisplay: 'narrowSymbol',
    });
  } catch {
    // Some engines reject narrowSymbol, and an unknown code throws outright.
    text = code
      ? `${abs.toLocaleString(undefined, opts)} ${code}`
      : `$${abs.toLocaleString(undefined, opts)}`;
  }
  if (n < 0) return `−${text}`;
  return sign ? `+${text}` : text;
}

export function pct(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const FULL_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                     'August', 'September', 'October', 'November', 'December'];

export function monthLabel(month, { long = false, full = false } = {}) {
  if (!month) return '—';
  const [y, m] = month.split('-').map(Number);
  if (full) return `${FULL_MONTHS[m - 1] ?? month} ${y}`;
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
