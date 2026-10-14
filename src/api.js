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
export const getAccounts     = () => req('/api/accounts');

/**
 * What to call an account so you can tell which it is: the bank, the kind of
 * account and its last four digits — "TD Bank · Chequing ••1234" — or her
 * nickname for it when she gave one. Falls back to the name the bank or the
 * statement gave it when the bank isn't known.
 */
export function accountTitle(a) {
  if (!a) return '';
  // Her nickname wins everywhere (Profile › Accounts).
  const base = a.nickname || (!a.institution ? (a.account_name || a.account_id)
    : `${a.institution} · ${a.kind_label}${a.mask ? ` ••${a.mask}` : ''}`);
  return a.joint ? `${base} · Joint with ${a.joint}` : base;
}
// On joint accounts, purchases at this name are always yours.
export const setMineAlways   = (id, on) =>
  json('PUT', `/api/transactions/${id}/mine-always`, { on });
// Profile › Accounts (Pearl AM-01 to AM-07, C-01, C-06).
export const getAccountsOverview = () => req('/api/accounts/overview');
// `counted`, `joint_share` (1–99 or null), `anchor`, `nickname`.
export const saveAccountSettings = (id, fields) =>
  json('PUT', `/api/accounts/${encodeURIComponent(id)}/settings`, fields);
export const addManualAccount = (name, kind, balance) =>
  json('POST', '/api/accounts/manual', { name, kind, balance });
export const updateManualBalance = (id, balance) =>
  json('PUT', `/api/accounts/${encodeURIComponent(id)}/balance`, { balance });
// `transactions` is 'keep' or 'delete'.
export const removeAccount = (id, transactions) =>
  json('POST', `/api/accounts/${encodeURIComponent(id)}/remove`, { transactions });
// "Same account as…": merge this account into `into`, for two copies of a card.
export const mergeAccount = (id, into) =>
  json('POST', `/api/accounts/${encodeURIComponent(id)}/merge`, { into });
export const keepAsManual = (id) =>
  json('POST', `/api/accounts/${encodeURIComponent(id)}/keep-as-manual`, {});
// Profile hub (S-01) and Categories and rules (S-03).
export const getProfileSummary = () => req('/api/profile');
export const getRules = () => req('/api/rules');
export const editRule = (id, category) =>
  json('PUT', `/api/rules/${encodeURIComponent(id)}`, { category });
export const deleteRule = (id) =>
  req(`/api/rules/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const getCategories   = () => req('/api/categories');

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
export const forgotPassword = (identifier) =>
  authPost('/api/auth/forgot', { identifier });
export const resetPassword  = (token, password) =>
  authPost('/api/auth/reset', { token, password });
// Pearl S-02: a code to the new address, then the code.
export const startEmailChange  = (email) => authPost('/api/auth/email/start', { email });
export const verifyEmailChange = (code) => authPost('/api/auth/email/verify', { code });

// Pearl: a six-digit code by email, and passkeys.
// `create` is true on the sign-up screen, where a new address makes an account.
export const startCode      = (email, firstName, create = false) =>
  authPost('/api/auth/code/start', { email, first_name: firstName, create });
export const verifyCode     = (email, code) =>
  authPost('/api/auth/code/verify', { email, code });
export const passkeyOptions = () => json('POST', '/api/auth/passkey/options', {});
export const passkeySignIn  = (credential) =>
  authPost('/api/auth/passkey/verify', credential);
export const passkeyRegisterOptions = () =>
  json('POST', '/api/auth/passkey/register/options', {});
export const passkeyRegister = (credential) =>
  json('POST', '/api/auth/passkey/register/verify', credential);

// Pearl A-07, A-08: a sign-in on a new browser waits for her other device to
// approve it, or for a recovery code (finance/devices.py).
export const askDeviceApproval = () => authPost('/api/auth/device/ask', {});
export async function deviceStatus() {
  const r = await fetch(`${API}/api/auth/device/status`, CREDENTIALS);
  const body = await r.json().catch(() => ({}));
  return { ok: r.ok, ...body };
}
export const signInWithRecoveryCode = (code) => authPost('/api/auth/device/recovery', { code });
export const cancelDeviceCheck = () => authPost('/api/auth/device/cancel', {});
// On her signed-in devices: what's waiting for approval, and her answer.
export const getApprovals   = () => req('/api/auth/approvals');
export const answerApproval = (id, approve) =>
  json('POST', `/api/auth/approvals/${id}`, { approve });
export const makeRecoveryCodes = () => json('POST', '/api/auth/recovery-codes', {});
// Onboarding: province, the Quebec waitlist, consents, which step you're on.
export const getOnboarding  = () => req('/api/onboarding');
export const saveOnboarding = (fields) => json('POST', '/api/onboarding', fields);

// ── Profile › Privacy (THL-115, THL-116, THL-117, THL-139) ──────────────────
// Consents with their dates, the change log, who to write to and the linked
// banks (T-04, CN-04).
export const getPrivacy = () => req('/api/privacy');
// Only the optional ones: ai_sort, tips, analytics (CN-04, CN-05).
export const setConsent = (key, value) => json('PUT', '/api/privacy/consents', { key, value });
export const getNotifications = () => req('/api/notifications');
export const saveNotifications = (changes) => json('PUT', '/api/notifications', changes);
// N-01: `answer` is 'on' or 'not_now'.
export const answerNotifyPrompt = (answer, milestone) =>
  json('POST', '/api/notifications/prompt', { answer, milestone });
// D-01 / D-02: what the .zip holds, and where to download it.
export const getExportSummary = () => req('/api/data/export');
export const exportUrl = () => `${API}/api/data/export.zip`;
// D-04: how she can confirm it's her, then the deletion itself.
export const getDeleteOptions = () => req('/api/account/delete');
export const deletePasskeyOptions = () => json('POST', '/api/account/delete/passkey-options', {});
export const sendDeleteCode = () => authPost('/api/account/delete/code', {});
export const deleteAccountNow = (proof) => authPost('/api/account/delete', proof);


// ── Plaid ────────────────────────────────────────────────────────────────────
// With an item id, Link opens in update mode to sign in to that bank again (C-04).
export const createLinkToken = (itemId) =>
  json('POST', '/api/plaid/link-token', itemId ? { item_id: itemId } : {});
export const exchangePublicToken = (publicToken, institution) =>
  json('POST', '/api/plaid/exchange',
       { public_token: publicToken, institution });
export const syncPlaid       = () => json('POST', '/api/plaid/sync', {});

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

// Goals (THL-131, THL-132, THL-179): the Anchor, treasure chests (the piggy
// banks above, by the Goals page's name) and the saving goal.
// Home (THL-44, THL-46): safe to spend for the month and every row behind it.
export const getHome = () => req('/api/home');
// The Path page (THL-129 GR-01), and one step with her numbers (GR-02 to GR-04).
export const getPath = () => req('/api/path');
export const getPathStep = (key) => req(`/api/path/step/${encodeURIComponent(key)}`);
// Where she starts (THL-130 GR-06, GR-07), at the end of onboarding.
export const getPlacement = () => req('/api/path/placement');
export const placeOnPath  = () => json('POST', '/api/path/placement', {});
// A phase done, once (GR-08 to GR-10), and GR-20's "Welcome back".
export const getMoments   = () => req('/api/moments');
export const seeMoment    = (phase) => json('POST', `/api/moments/${encodeURIComponent(phase)}`, {});
// Learn (THL-134 GR-11 to GR-14): her place in each module, saved per screen.
export const getLearn     = () => req('/api/learn');
export const saveLearn    = (id, body) => json('PUT', `/api/learn/${encodeURIComponent(id)}`, body);
// The starter questions (E-02) and "Use a different amount" (E-03).
// Last month's surplus or shortfall (THL-212): "now", "spread2", "spread3",
// or "save", "chest", "spend".
export const answerCarryover = (month, choice) =>
  json('PUT', `/api/carryover/${month}`, { choice });

// Trips (THL-174): a date range whose spending becomes Travel, on its own.
export const getTrips    = () => req('/api/trips');
export const previewTrip = (start, end, tripId = null) =>
  json('POST', '/api/trips/preview', { start, end, trip_id: tripId });
export const saveTrip    = (trip) => (trip.id
  ? json('PUT', `/api/trips/${trip.id}`, trip)
  : json('POST', '/api/trips', trip));
export const deleteTrip  = (id) => req(`/api/trips/${id}`, { method: 'DELETE' });
export const putHomeAnswers = (answers) => json('PUT', '/api/home/answers', answers);
// Month or week as Home's main view (THL-166), saved on her account.
// "Can I afford it?" (THL-167): works it out and records nothing.
export const checkAfford = (amount) => json('POST', '/api/home/afford', { amount });
// Category budgets (THL-168): each one a percent of her usual month.
export const getCategoryBudgets = () => req('/api/category-budgets');
export const putCategoryBudget = (category, pct) => json('PUT', '/api/category-budgets', { category, pct });
// Recommendation cards (THL-12): "Not for me" hides a type for 30 days.
export const dismissSuggestion = (type) => json('PUT', `/api/recommendations/${type}/dismiss`, {});
export const undoDismissSuggestion = (type) => req(`/api/recommendations/${type}/dismiss`, { method: 'DELETE' });
// Debts (THL-49): every debt, and the rate and minimum she adds (D-03).
export const getDebts = () => req('/api/debts');
export const putDebtDetails = (accountId, fields) =>
  json('PUT', `/api/debts/${encodeURIComponent(accountId)}`, fields);
export const getGoals        = () => req('/api/goals');
export const setAnchor       = (fields) => json('PUT', '/api/goals/anchor', fields);
export const setUnusualMonths = (months) => json('PUT', '/api/goals/anchor/unusual', { months });
// Growth › Insights (THL-186, THL-196): the month, a month left out of the
// usual (THL-59), and Keep or Review on a subscription (THL-63).
export const getInsightsMonth = (month) =>
  req(`/api/insights/month${month ? `?month=${encodeURIComponent(month)}` : ''}`);
export const setMonthUnusual = (month, unusual) =>
  json('PUT', '/api/insights/unusual', { month, unusual });
export const setSubscriptionChoice = (merchant, choice) =>
  json('PUT', '/api/insights/subscriptions', { merchant, choice });
export const anchorWhatIf    = (monthly) =>
  req(`/api/goals/anchor/whatif?monthly=${encodeURIComponent(monthly)}`);
export const getChest        = (id) => req(`/api/goals/chests/${id}`);
export const openTreasure    = (id, txnIds, categories) =>
  json('POST', `/api/goals/chests/${id}/open`, { txn_ids: txnIds, categories });
export const seenCatchUp     = (id, monthly) =>
  json('PUT', `/api/goals/chests/${id}/seen`, { monthly });
export const addToChest      = (id, amount) =>
  json('POST', `/api/goals/chests/${id}/add`, { amount });


// Income and bills (THL-45, THL-127 I-01 to I-06): the check after linking,
// and Profile › Income and bills. Every call returns the whole check.
const IB = '/api/income-bills';
const billPath = (key) => `${IB}/bills/${encodeURIComponent(key)}`;
export const getIncomeBills   = () => req(IB);
export const answerPay        = (payer, answer) => json('POST', `${IB}/pay/answer`, { payer, answer });
export const addPay           = (pay) => json('POST', `${IB}/pay`, pay);
export const editPay          = (id, pay) => json('PUT', `${IB}/pay/${encodeURIComponent(id)}`, pay);
export const saveExpected     = (amount, varies) => json('PUT', `${IB}/expected`, { amount, varies });
export const skipExpected     = () => json('POST', `${IB}/expected/skip`, {});
// "Use Pearl's estimate": her own amount goes.
export const clearExpected    = () => req(`${IB}/expected`, { method: 'DELETE' });
export const confirmBills     = (ticked) => json('PUT', `${IB}/bills`, { ticked });
export const addBill          = (bill) => json('POST', `${IB}/bills`, bill);
export const editBill         = (key, bill) => json('PUT', billPath(key), bill);
export const removeBill       = (key) => req(billPath(key), { method: 'DELETE' });
export const answerRent       = (key) => json('POST', `${IB}/rent`, { key, answer: 'yes' });


// Growth › Projections (THL-197 GR-33 to GR-36): this month, the next 30
// days and savings in a year, with `extra` dollars more a month as the
// what-if; "Use this pace for my Anchor" sets the monthly saving goal.
export const getProjections  = (extra = 0) =>
  req(`/api/projections${extra > 0 ? `?extra=${encodeURIComponent(extra)}` : ''}`);
export const setSavingPace   = (monthly) => json('PUT', '/api/projections/pace', { monthly });
// Unveil (THL-135 GR-16, THL-195 GR-37): the readiness checklist, and
// "Opened an investing account?" — the kind of account only.
export const getUnveil       = () => req('/api/unveil');
export const reportInvesting = (type, via) => json('PUT', '/api/unveil', via ? { type, via } : { type });
export const undoInvesting   = () => req('/api/unveil', { method: 'DELETE' });
// The partner handoff (THL-136 GR-19 to GR-23, post-MVP, only when one is
// configured): the link out, GR-20's "Not yet", GR-22's "Tell me when".
export const goToPartner     = () => json('POST', '/api/unveil/partner', {});
export const partnerNotYet   = () => json('PUT', '/api/unveil/partner/welcome', { answer: 'not_yet' });
export const partnerNotify   = () => json('PUT', '/api/unveil/partner/notify', {});

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

// The transactions list (THL-122): a page of rows, the totals above them,
// and — with a group or category chosen — that total against a usual month.
export function getTxList(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) params.set(k, v);
  });
  return req(`/api/transactions/list?${params}`);
}
export const getTx       = (id) => req(`/api/transactions/${encodeURIComponent(id)}`);
export const confirmTx   = (id) => json('PUT', `/api/transactions/${encodeURIComponent(id)}/confirm`, {});
export const setTxNote   = (id, note) =>
  json('PUT', `/api/transactions/${encodeURIComponent(id)}/note`, { note });

// How much of a charge was yours, when friends paid you back the rest.
// null puts the whole charge back.
export const setShare      = (id, myShare) =>
  json('PUT', `/api/transactions/${id}/share`, { my_share: myShare });
// Money into a joint account: who put it in, 'me' or 'them' (null asks
// again); `remember` answers for every deposit from that sender.
// Who an e-Transfer was from or to; '' goes back to the bank's name.
export const setParty      = (id, name) =>
  json('PUT', `/api/transactions/${id}/party`, { name });
export const setJointFrom  = (id, who, remember = false) =>
  json('PUT', `/api/transactions/${id}/joint-from`, { who, remember });
// Say where a group of transfers went; `remember` makes it the rule for
// those names.
export const sortTransfers = (ids, category, remember) =>
  json('POST', '/api/transfers/sort', { ids, category, remember });
// Money a friend sent back, linked to the charge it repays.
export const linkPayback   = (id, inflowId, person) =>
  json('POST', `/api/transactions/${id}/paybacks/${inflowId}`, person ? { person } : {});
// A charge split with people (S-01, THL-124): {mode, people: [{name, amount}], watch}.
export const setSplit      = (id, split) => json('PUT', `/api/transactions/${id}/split`, split);
export const clearSplit    = (id) =>
  req(`/api/transactions/${id}/split`, { method: 'DELETE' });
export const unlinkPayback = (id, inflowId) =>
  req(`/api/transactions/${id}/paybacks/${inflowId}`, { method: 'DELETE' });
export const setCategory   = (id, category, applyToMerchant = false) =>
  json('PATCH', `/api/transactions/${id}`, {
    category, apply_to_merchant: applyToMerchant,
  });
// What a category would do before it is saved (R-02), and taking a change
// back — rows and rules — with the `undo` a change returned (R-03).
export const previewCategory = (id, category, applyToMerchant = false) =>
  json('POST', `/api/transactions/${id}/category/preview`, {
    category, apply_to_merchant: applyToMerchant,
  });
export const undoChange = (undo) => json('POST', '/api/transactions/undo', undo);

// Leaving one transaction out, and putting it back (the rules that leave
// every one like it out are on Profile › Categories and rules).
export const excludeTransaction = (id, reason) =>
  json('PUT', `/api/transactions/${id}/exclude`, { reason });
export const includeTransaction = (id) =>
  req(`/api/transactions/${id}/exclude`, { method: 'DELETE' });

// What kind of income a deposit is: salary, bonus, interest, gifts,
// government, tax_refund or other.
export const INCOME_KINDS = {
  salary: 'Salary', bonus: 'Bonus / irregular', interest: 'Interest',
  gifts: 'Gifts received', government: 'Government credits',
  tax_refund: 'Tax refund', other: 'Other income',
};
export const setIncomeType = (id, kind) =>
  json('PUT', `/api/transactions/${id}/income-type`, { kind });

// Everything Pearl isn't sure about, each with its best guess.
export const getReview     = () => req('/api/review');
export const dismissReview = (key) => json('POST', '/api/review/dismiss', { key });
// Needs a look's Skipped (THL-213): into Skipped, or back to the queue.
export const skipReview = (key, skip = true) => json('POST', '/api/review/skip', { key, skip });

// "This was a one-off" (THL-71): out of her usual month, still in its own.
export const setOneOff = (id, on) =>
  json('PUT', `/api/transactions/${encodeURIComponent(id)}/one-off`, { on });
// "Is this the same purchase?" (THL-165): answer is 'same' or 'different'.
export const answerDuplicate = (id, answer) =>
  json('POST', `/api/review/duplicates/${encodeURIComponent(id)}`, { answer });
// Keyboard review (THL-83): many rows at once, never a merchant rule.
export const previewBatchCategory = (ids, category) =>
  json('POST', '/api/transactions/batch/category/preview', { ids, category });
export const batchCategory = (ids, category) =>
  json('POST', '/api/transactions/batch/category', { ids, category });
export const batchConfirm = (ids) => json('POST', '/api/transactions/batch/confirm', { ids });
// Her preferences: single-key shortcuts on or off (WCAG 2.1.4).
export const getPreferences = () => req('/api/preferences');
export const savePreferences = (prefs) => json('PUT', '/api/preferences', prefs);

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
