import { useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, MerchantMark, Notice, StatusPill,
} from '../components/ui.jsx';
import {
  accountTitle, addTransaction, allocateToBank, dateLabel, deleteTransaction, getBanks,
  getPaybacks, getSaved, getTransactions, getUnsorted, linkPayback, money,
  setCategory, setInvested, setMineAlways, setShare, sortTransfers, unallocate,
  unlinkPayback,
  unsortTransaction,
} from '../api.js';

// Never offered as "where it went": these aren't spending.
const NOT_SPENT = new Set(['Income', 'Transfers', 'Saved', 'Unsorted transfers']);

const PAGE = 100;

const today = () => new Date().toISOString().slice(0, 10);

export default function TransactionsPanel({ summary, categories, accounts, onChanged }) {
  const [filters, setFilters] = useState({ month: '', category: '', account: '', q: '' });
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [charging, setCharging] = useState(null);
  const [splitting, setSplitting] = useState(null);
  const [banks, setBanks] = useState([]);
  const [reload, setReload] = useState(0);

  // Loaded once: the list of banks changes on its own tab, not here.
  useEffect(() => {
    getBanks().then((d) => setBanks(d.banks ?? [])).catch(() => setBanks([]));
  }, [reload]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getTransactions({ ...filters, limit: PAGE, offset: page * PAGE })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e); });
    return () => { cancelled = true; };
  }, [filters, page, reload]);

  /** Refetch this page and let the rest of the app know the totals moved. */
  function bump() {
    setReload((n) => n + 1);
    onChanged?.();
  }

  async function removeRow(txn) {
    if (!window.confirm(`Delete ${txn.merchant} ${money(txn.amount, { cents: true })}?`)) return;
    await deleteTransaction(txn.id);
    setReload((n) => n + 1);
    onChanged?.();
  }

  function update(key, value) {
    setPage(0);
    setFilters((f) => ({ ...f, [key]: value }));
  }

  async function recategorize(txn, category, applyToMerchant) {
    await setCategory(txn.id, category, applyToMerchant);
    setEditing(null);
    const fresh = await getTransactions({ ...filters, limit: PAGE, offset: page * PAGE });
    setData(fresh);
    onChanged?.();
  }

  const rows = data?.transactions ?? [];
  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE);

  return (
    <div className="stack">
      <WhereDidThisGo categories={categories} reload={reload} onDone={bump} />
      <AddByHand categories={categories}
                 onAdded={() => { setReload((n) => n + 1); onChanged?.(); }} />

      {/* Filters sit in one row above the data, as a single control group. */}
      <Card>
        <div className="controls">
          <label htmlFor="f-month">Month</label>
          <select id="f-month" value={filters.month} onChange={(e) => update('month', e.target.value)}>
            <option value="">All</option>
            {[...(summary.months ?? [])].reverse().map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>

          <label htmlFor="f-cat">Category</label>
          <select id="f-cat" value={filters.category} onChange={(e) => update('category', e.target.value)}>
            <option value="">All</option>
            <option value="__unsure__">Not sure</option>
            {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>

          <label htmlFor="f-acct">Card</label>
          <select id="f-acct" value={filters.account} onChange={(e) => update('account', e.target.value)}>
            <option value="">All</option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>{accountTitle(a)}</option>
            ))}
          </select>

          <input
            type="search"
            value={filters.q}
            onChange={(e) => update('q', e.target.value)}
            placeholder="Search merchant or description"
            style={{ flex: 1, minWidth: 200 }}
            aria-label="Search transactions"
          />
        </div>
      </Card>

      <ErrorNote error={error} />

      <Card
        title={`${total.toLocaleString()} transaction${total === 1 ? '' : 's'}`}
      >
        {!data ? <Loading what="transactions" /> : (
          <>
            <div className="table-wrap">
              <table className="stacked">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Merchant</th>
                    <th>Category</th>
                    <th>Card</th>
                    <th>Piggy bank</th>
                    <th>Your share</th>
                    <th className="r">Amount</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id}>
                      <td className="muted">{dateLabel(t.date)}</td>
                      <td className="merchant">
                        <MerchantMark logo={t.logo} name={t.merchant} />
                        {t.merchant}
                        {t.source === 'manual' && (
                          <span className="pill" style={{ marginLeft: 8 }}>by hand</span>
                        )}
                        <div className="desc" title={t.description}>
                          {t.description}
                        </div>
                      </td>
                      <td>
                        {editing === t.id ? (
                          <CategoryEditor
                            current={t.category}
                            merchant={t.merchant}
                            categories={categories}
                            onCancel={() => setEditing(null)}
                            onSave={(cat, all) => recategorize(t, cat, all)}
                          />
                        ) : (
                          <button className="btn quiet" onClick={() => setEditing(t.id)}>
                            {t.category}
                            {t.category_source === 'user' && ' ✓'}
                            {t.unsure && (
                              <span className="unsure" title="Plaid wasn't sure of this one">?</span>
                            )}
                          </button>
                        )}
                      </td>
                      <td className="muted">{t.account_name}</td>
                      <td>
                        <BankCell
                          txn={t} banks={banks}
                          open={charging === t.id}
                          onOpen={() => setCharging(charging === t.id ? null : t.id)}
                          // Deliberately left open: the row has just told you
                          // how much the bank could pay and how much stayed in
                          // the month, and closing it would take that away
                          // before it was read.
                          onDone={bump}
                        />
                      </td>
                      <td>
                        {t.joint ? (
                          <OwnerCell txn={t}
                                     open={splitting === t.id}
                                     onOpen={() => setSplitting(splitting === t.id ? null : t.id)}
                                     onDone={() => { setSplitting(null); bump(); }} />
                        ) : (
                        <ShareCell
                          txn={t}
                          open={splitting === t.id}
                          onOpen={() => setSplitting(splitting === t.id ? null : t.id)}
                          onDone={() => { setSplitting(null); bump(); }}
                        />
                        )}
                      </td>
                      <td className="r" style={t.amount < 0 ? { color: 'var(--good-text)' } : undefined}>
                        {money(t.amount, { cents: true })}
                        {t.my_share != null && !t.joint && (
                          <div className="share-note num">
                            yours {money(t.my_share, { cents: true })}
                          </div>
                        )}
                        {t.my_share == null && t.paid_back > 0 && (
                          <div className="share-note num">
                            yours {money(Math.max(t.amount - t.paid_back, 0), { cents: true })}
                          </div>
                        )}
                        {t.invested != null && (
                          <div className="share-note num">
                            saved {money(t.invested, { cents: true })}
                          </div>
                        )}
                        {t.repays && (
                          <div className="share-note">
                            paid back · {t.repays_merchant}
                            {t.repays_amount != null && ` ${money(t.repays_amount)}`}
                          </div>
                        )}
                      </td>
                      <td className="r">
                        {/* Only hand-typed rows are deletable. An imported row
                            would come straight back on the next import, so
                            offering to delete it would be a lie. */}
                        {t.source === 'manual' && (
                          <button className="btn quiet" onClick={() => removeRow(t)}>
                            Delete
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {pages > 1 && (
              <div className="row" style={{ marginTop: 14 }}>
                <button className="btn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  ← Previous
                </button>
                <span className="muted small">Page {page + 1} of {pages}</span>
                <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

/**
 * Add a purchase before the statement arrives.
 *
 * The hazard is obvious — the statement shows up later carrying the same
 * purchase — and it is handled in both directions. Entering one runs the same
 * duplicate check an import runs, only looser, because a hand-typed date drifts
 * a day or two and the descriptor never matches the card's. A near match is
 * *shown*, not silently merged: this form reports what it found and you decide.
 * Going the other way, the statement's version replaces what you typed.
 */
function AddByHand({ categories, onAdded }) {
  const blank = { date: today(), description: '', amount: '', category: '' };
  const [draft, setDraft] = useState(blank);
  const [open, setOpen] = useState(false);
  const [conflict, setConflict] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(null);

  async function submit(e, confirm = false) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await addTransaction({
        ...draft, amount: Number(draft.amount), confirm,
      });
      if (r.conflict) {
        setConflict(r);
        return;
      }
      setAdded(r);
      setConflict(null);
      setDraft({ ...blank });
      onAdded?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const set = (k) => (e) => {
    setConflict(null);
    setAdded(null);
    setDraft({ ...draft, [k]: e.target.value });
  };

  if (!open) {
    return (
      <div className="row">
        <button className="btn primary" onClick={() => setOpen(true)}>
          + Add a transaction by hand
        </button>
      </div>
    );
  }

  return (
    <Card title="Add a transaction by hand"
          actions={<button className="btn quiet" onClick={() => setOpen(false)}>Close</button>}>
      <form className="controls" onSubmit={(e) => submit(e, false)}>
        <label htmlFor="m-date">Date</label>
        <input id="m-date" type="date" required value={draft.date} onChange={set('date')} />

        <input type="text" required value={draft.description} onChange={set('description')}
               placeholder="What was it?" aria-label="Description"
               style={{ flex: '1 1 200px' }} />

        <label htmlFor="m-amount">Amount</label>
        <input id="m-amount" type="number" step="0.01" required value={draft.amount}
               onChange={set('amount')} placeholder="0.00" style={{ width: 110 }} />

        <select value={draft.category} onChange={set('category')} aria-label="Category">
          <option value="">Categorize it for me</option>
          {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>

        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Checking…' : 'Add'}
        </button>
      </form>


      <ErrorNote error={error} />

      {added && (
        <Notice kind="good">
          Added · <strong>{added.merchant}</strong> · {added.category}
        </Notice>
      )}

      {conflict && (
        <div className="verdict">
          <div className="line">
            <StatusPill state={conflict.duplicate ? 'critical' : 'warning'}>
              {conflict.duplicate ? 'Already there' : 'Looks familiar'}
            </StatusPill>
            <span>
              {conflict.duplicate
                ? conflict.error
                : 'Found something matching the amount already in your ledger.'}
            </span>
          </div>

          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>Date</th><th>Merchant</th><th>Card</th>
                  <th className="r">Amount</th><th>Match</th>
                </tr>
              </thead>
              <tbody>
                {(conflict.matches ?? []).map((m) => (
                  <tr key={m.id}>
                    <td className="muted">{dateLabel(m.date)}</td>
                    <td className="merchant">{m.merchant}</td>
                    <td className="muted">{m.account}</td>
                    <td className="r num">{money(m.amount, { cents: true })}</td>
                    <td>
                      <span className={`pill ${m.confidence === 'high' ? 'warning' : ''}`}>
                        {m.days_apart === 0 ? 'same day'
                          : `${m.days_apart} day${m.days_apart === 1 ? '' : 's'} apart`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!conflict.duplicate && (
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn primary" disabled={busy}
                      onClick={(e) => submit(e, true)}>
                It&apos;s a different purchase — add it
              </button>
              <button className="btn quiet" onClick={() => setConflict(null)}>
                Never mind
              </button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function CategoryEditor({ current, merchant, categories, onSave, onCancel }) {
  const [value, setValue] = useState(current);

  return (
    <div className="row" style={{ gap: 6 }}>
      <select value={value} onChange={(e) => setValue(e.target.value)} autoFocus
              aria-label="Category">
        {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
      </select>
      <button className="btn" onClick={() => onSave(value, false)}>This one</button>
      <button className="btn primary" onClick={() => onSave(value, true)}
              title={`Apply to every charge from ${merchant}, now and in future imports`}>
        All {merchant}
      </button>
      <button className="btn quiet" onClick={onCancel}>Cancel</button>
    </div>
  );
}

// Set by "See what's counted" on Ahead, so this card opens on Saved.
export const OPEN_SAVED_KEY = 'spendie.openSaved';

function wantsSaved() {
  try {
    const v = window.sessionStorage.getItem(OPEN_SAVED_KEY);
    window.sessionStorage.removeItem(OPEN_SAVED_KEY);
    return v === '1';
  } catch {
    return false;
  }
}

const SHOWN = 5;

function span(first, last) {
  return first === last ? dateLabel(first) : `${dateLabel(first)} – ${dateLabel(last)}`;
}

/**
 * Money that left a bank account for somewhere Spendie can't see.
 *
 * Every dollar out was spent or saved. Until you say which, it counts as
 * spent. One row per recipient, so twelve e-transfers to one person are one
 * decision; whatever you decide can be undone, here or under Saved.
 */
function WhereDidThisGo({ categories, reload, onDone }) {
  const [data, setData] = useState(null);
  const [saved, setSaved] = useState(null);
  const [view, setView] = useState(() => (wantsSaved() ? 'saved' : 'sort'));
  const [remember, setRemember] = useState(true);
  const [picking, setPicking] = useState(null);
  const [done, setDone] = useState([]);
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getUnsorted().then(setData).catch(() => setData(null));
    getSaved().then(setSaved).catch(() => setSaved(null));
  }, [reload]);

  const groups = data?.groups ?? [];
  const savedRows = saved?.rows ?? [];
  if (!groups.length && !savedRows.length && !done.length) return null;
  const spendable = categories.filter((c) => !NOT_SPENT.has(c.name));

  async function run(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const decide = (g, category) => run(async () => {
    await sortTransfers(g.ids, category, remember);
    setPicking(null);
    setDone((d) => [{ ...g, category }, ...d.filter((x) => x.key !== g.key)]);
  });

  const undoGroup = (g) => run(async () => {
    for (const id of g.ids) await unsortTransaction(id);
    setDone((d) => d.filter((x) => x.key !== g.key));
  });

  const undoRow = (r) => run(() => unsortTransaction(r.id));

  const shown = all ? groups : groups.slice(0, SHOWN);

  // Nothing waiting: just a way into what's saved.
  if (!groups.length && !done.length && view !== 'saved') {
    return (
      <button type="button" className="card saved-peek" onClick={() => setView('saved')}>
        <span>Saved</span>
        <span className="num">{money(saved?.total ?? 0)} ▸</span>
      </button>
    );
  }

  return (
    <Card className="sort-card">
      <div className="sort-head">
        <h2>Where did this go?</h2>
        <div className="segmented small" role="group" aria-label="Show">
          <button aria-pressed={view === 'sort'} onClick={() => setView('sort')}>
            To sort{groups.length ? ` · ${data.count}` : ''}
          </button>
          <button aria-pressed={view === 'saved'} onClick={() => setView('saved')}>
            Saved · {money(saved?.total ?? 0)}
          </button>
        </div>
      </div>

      {view === 'sort' ? (
        <>
          {groups.length > 0 && (
            <p className="muted small sort-note">
              {money(data.total)} counted as spent until sorted
            </p>
          )}
          <ul className="sort-list">
            {done.map((g) => (
              <li key={`done-${g.key}`} className="sort-row done">
                <span className="muted">
                  {g.merchant} → <strong>{g.category}</strong>
                </span>
                <button className="link-btn" disabled={busy} onClick={() => undoGroup(g)}>
                  Undo
                </button>
              </li>
            ))}
            {shown.map((g) => (
              <li key={g.key} className="sort-row">
                <div className="sort-what">
                  <strong>{g.merchant}</strong>
                  <div className="muted small">
                    {g.count > 1 ? `${g.count} transfers · ` : ''}
                    {g.accounts.filter(Boolean).join(', ')}
                    {' · '}{span(g.first, g.last)}
                  </div>
                </div>
                <div className="sort-side">
                  <span className="num sort-amt">{money(g.total)}</span>
                  {picking === g.key ? (
                    <select aria-label={`Spent on — ${g.merchant}`} value="" disabled={busy}
                            // eslint-disable-next-line jsx-a11y/no-autofocus
                            autoFocus onBlur={() => setPicking(null)}
                            onChange={(e) => e.target.value && decide(g, e.target.value)}>
                      <option value="">Spent on…</option>
                      {spendable.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  ) : (
                    <>
                      <button className="pill-btn" disabled={busy}
                              onClick={() => decide(g, 'Saved')}>Saved</button>
                      <button className="pill-btn" disabled={busy}
                              onClick={() => setPicking(g.key)}>Spent</button>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {groups.length > SHOWN && (
            <button className="link-btn" onClick={() => setAll((a) => !a)}>
              {all ? 'Show fewer' : `Show ${groups.length - SHOWN} more`}
            </button>
          )}
          {groups.length > 0 && (
            <label className="sort-foot small muted">
              <input type="checkbox" checked={remember}
                     onChange={(e) => setRemember(e.target.checked)} />
              Remember where these go
            </label>
          )}
        </>
      ) : (
        <>
          {savedRows.length === 0 ? (
            <p className="muted small">Nothing marked as saved in the last two months.</p>
          ) : (
            <ul className="sort-list">
              {savedRows.map((r) => (
                <li key={r.id} className="sort-row">
                  <div className="sort-what">
                    <strong>{r.merchant}</strong>
                    <div className="muted small">
                      {dateLabel(r.date)} · {r.account_name}
                      {r.part && ` · part of ${money(r.amount)}`}
                    </div>
                  </div>
                  <div className="sort-side">
                    <span className="num sort-amt">{money(r.saved)}</span>
                    <button className="link-btn" disabled={busy} onClick={() => undoRow(r)}>
                      Undo
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="sort-foot small">
            <span className="muted">Since {dateLabel(saved?.since)}</span>
            <strong className="num">{money(saved?.total ?? 0)}</strong>
          </div>
        </>
      )}
      <ErrorNote error={error} />
    </Card>
  );
}

/**
 * How much of a charge was yours, when friends paid you back the rest.
 *
 * Only your share counts toward the week, the month and the budgets, in the
 * month it was spent. The card's amount stays as charged beside it.
 *
 * The easy way is to tick the e-transfers that paid you back: your share is
 * what is left, and that money in stops looking like money you made.
 */
function ShareCell({ txn, open, onOpen, onDone }) {
  const [value, setValue] = useState('');
  // How much of it was put away, when part of it was.
  const [invested, setInvestedValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [paybacks, setPaybacks] = useState(null);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    if (open) {
      setValue(txn.my_share != null ? String(txn.my_share) : '');
      setInvestedValue(txn.invested != null ? String(txn.invested) : '');
      setChanged(false);
      if (txn.amount > 0) {
        getPaybacks(txn.id).then(setPaybacks).catch(() => setPaybacks(null));
      }
    }
  }, [open, txn.id, txn.my_share, txn.invested, txn.amount]);

  if (txn.amount <= 0) return <span className="muted small">—</span>;

  async function save(share, inv = invested === '' ? null : Number(invested)) {
    setBusy(true);
    setError(null);
    try {
      await setShare(txn.id, share);
      if (inv !== (txn.invested ?? null)) await setInvested(txn.id, inv);
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(inflow, on) {
    setBusy(true);
    setError(null);
    try {
      setPaybacks(on ? await linkPayback(txn.id, inflow.id)
                     : await unlinkPayback(txn.id, inflow.id));
      setChanged(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const paidBack = txn.paid_back ?? 0;
  if (!open) {
    return (
      <button className="btn quiet" onClick={onOpen}>
        {txn.my_share != null ? `Yours ${money(txn.my_share)}`
          : paidBack > 0 ? `Yours ${money(Math.max(txn.amount - paidBack, 0))}`
          : txn.invested != null ? `Saved ${money(txn.invested)}` : 'Split…'}
      </button>
    );
  }

  const part = (n) => (Math.round((txn.amount / n) * 100) / 100).toFixed(2);
  const linked = paybacks?.linked ?? [];
  const offered = [...linked.map((t) => ({ ...t, on: true })),
                   ...(paybacks?.candidates ?? []).map((t) => ({ ...t, on: false }))];

  return (
    <form className="stack share-edit" style={{ gap: 6 }}
          onSubmit={(e) => { e.preventDefault(); save(value === '' ? null : Number(value)); }}>
      {offered.length > 0 && (
        <fieldset className="paybacks">
          <legend className="small">Paid back by</legend>
          {offered.map((t) => (
            <label key={t.id} className="row small" style={{ gap: 6 }}>
              <input type="checkbox" checked={t.on} disabled={busy}
                     onChange={(e) => toggle(t, e.target.checked)} />
              <span className="num">{money(-t.amount, { cents: true })}</span>
              <span className="muted">{dateLabel(t.date)} · {t.merchant}</span>
            </label>
          ))}
          {paybacks && (
            <div className="small">
              Your share: <strong className="num">{money(paybacks.share, { cents: true })}</strong>
              {' '}of {money(txn.amount, { cents: true })}
            </div>
          )}
        </fieldset>
      )}
      <div className="row" style={{ gap: 6 }}>
        <span className="muted small">Your share $</span>
        <input type="number" min="0" max={txn.amount} step="0.01" inputMode="decimal"
               value={value} onChange={(e) => setValue(e.target.value)}
               aria-label={`Your share of ${txn.merchant}`} style={{ width: 100 }} />
      </div>
      <div className="row" style={{ gap: 4 }}>
        {[[2, '½'], [3, '⅓'], [4, '¼']].map(([n, label]) => (
          <button key={n} type="button" className="btn quiet chip-btn"
                  onClick={() => setValue(part(n))}>{label}</button>
        ))}
      </div>
      <div className="row" style={{ gap: 6 }}>
        <span className="muted small">Saved $</span>
        <input type="number" min="0" max={txn.amount} step="0.01" inputMode="decimal"
               value={invested} onChange={(e) => setInvestedValue(e.target.value)}
               aria-label={`Saved part of ${txn.merchant}`} style={{ width: 90 }} />
        <button type="button" className="btn quiet chip-btn"
                onClick={() => setInvestedValue(txn.amount.toFixed(2))}>All</button>
      </div>
      <div className="row" style={{ gap: 6 }}>
        <button className="btn primary" type="submit" disabled={busy}>Save</button>
        {(txn.my_share != null || txn.invested != null) && (
          <button className="btn quiet" type="button" disabled={busy}
                  onClick={() => save(null, null)}>Clear</button>
        )}
        <button className="btn quiet" type="button"
                onClick={changed ? onDone : onOpen}>{changed ? 'Done' : 'Cancel'}</button>
      </div>
      <ErrorNote error={error} />
    </form>
  );
}

/**
 * Whose a row on a joint account was. Another member's by default; yours, or
 * part yours, when you say so. "Always mine" covers a name for good.
 */
function OwnerCell({ txn, open, onOpen, onDone }) {
  const full = txn.amount;
  const mine = txn.share_set && Math.abs((txn.my_share ?? 0) - full) < 0.005;
  const theirs = Math.abs(txn.my_share ?? 0) < 0.005;
  const [mode, setMode] = useState('theirs');
  const [part, setPart] = useState('');
  const [always, setAlways] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setMode(mine ? 'mine' : theirs ? 'theirs' : 'part');
      setPart(!mine && !theirs ? String(Math.abs(txn.my_share)) : '');
      setAlways(false);
    }
  }, [open, mine, theirs, txn.my_share]);

  const label = mine ? 'Mine' : theirs ? `${txn.joint}'s`
    : `Yours ${money(Math.abs(txn.my_share), { cents: true })}`;

  if (!open) {
    return (
      <button className={`owner-pill${theirs ? ' theirs' : ''}`} onClick={onOpen}>
        {label}
      </button>
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const sign = full < 0 ? -1 : 1;
      const share = mode === 'mine' ? full
        : mode === 'theirs' ? null : sign * Math.abs(Number(part));
      await setShare(txn.id, share);
      if (always && mode === 'mine') await setMineAlways(txn.id, true);
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack share-edit" style={{ gap: 6 }}>
      <div className="segmented small" role="group" aria-label="Whose was it">
        {[['mine', 'Mine'], ['theirs', 'Not mine'], ['part', 'Part']].map(([k, l]) => (
          <button key={k} type="button" aria-pressed={mode === k} onClick={() => setMode(k)}>{l}</button>
        ))}
      </div>
      {mode === 'part' && (
        <div className="row" style={{ gap: 6 }}>
          <span className="muted small">Yours $</span>
          <input type="number" min="0" max={Math.abs(full)} step="0.01" inputMode="decimal"
                 value={part} onChange={(e) => setPart(e.target.value)}
                 aria-label={`Your part of ${txn.merchant}`} style={{ width: 100 }} />
        </div>
      )}
      {mode === 'mine' && full > 0 && (
        <label className="small muted row" style={{ gap: 6 }}>
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          Always mine at “{txn.merchant}”
        </label>
      )}
      <div className="row" style={{ gap: 6 }}>
        <button className="btn primary" type="button" disabled={busy || (mode === 'part' && !part)}
                onClick={save}>Save</button>
        <button className="btn quiet" type="button" onClick={onOpen}>Cancel</button>
      </div>
      <ErrorNote error={error} />
    </div>
  );
}

/**
 * Which piggy bank pays for a charge, if any.
 *
 * Most charges get here by themselves: a bank that pays for Travel pays for
 * every travel charge, marked "automatic". This cell is for the exceptions —
 * a one-off in some other category charged to a bank by hand, or a travel
 * charge you would rather count as everyday spending. A charge a bank pays
 * leaves the week it fell in — it is not in the Overview, the budgets, or the
 * weekly number — because the bank's monthly contribution already paid for it.
 *
 * Only outflows can be charged: a refund or a card payment is money coming
 * back, and there is nothing to take out of a bank.
 */
function BankCell({ txn, banks, open, onOpen, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const bank = banks.find((b) => b.id === txn.bank_id);

  async function charge(id) {
    setBusy(true);
    setError(null);
    try {
      if (id) {
        setResult(await allocateToBank(Number(id), txn.id));
      } else {
        await unallocate(txn.id);
        setResult(null);
      }
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (txn.amount <= 0) {
    return <span className="muted small">—</span>;
  }

  if (banks.length === 0) {
    return <span className="muted small">—</span>;
  }

  if (bank && !open) {
    return (
      <button className="btn quiet" onClick={onOpen} disabled={busy}
              title={txn.bank_auto
                ? `${bank.name} pays for ${txn.category} — not counted in your week`
                : `Charged to ${bank.name} — not counted in your week`}>
        {bank.name} ✓
        {txn.bank_auto && <span className="muted"> · automatic</span>}
      </button>
    );
  }

  if (!open) {
    return (
      <button className="btn quiet" onClick={onOpen} disabled={busy}>
        Charge…
      </button>
    );
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <select value={txn.bank_id ?? ''} disabled={busy}
              aria-label="Charge this to a piggy bank"
              onChange={(e) => charge(e.target.value)}>
        <option value="">Count as everyday</option>
        {/* Nothing is disabled by what is left. A bank pays the charge even
            past its target, and repays the difference next year — so what
            matters at the point of choosing is which bank the spending
            belongs to, with what is left as context. */}
        {banks.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name} — {b.available >= 0
              ? `${money(b.available)} left`
              : `${money(-b.available)} over`}
          </option>
        ))}
      </select>
      {result && (
        <span className="small">
          {result.over
            ? <>{result.bank} paid it and is now{' '}
                <strong className="num">{money(result.behind_by)}</strong>{' '}
                over this year — next year&apos;s contribution repays it.</>
            : <>{result.bank} paid it —{' '}
                <strong className="num">{money(result.available)}</strong>{' '}
                left this year.</>}
        </span>
      )}
      <button className="btn quiet" onClick={onOpen} disabled={busy}>Close</button>
      {error && <span className="small" style={{ color: 'var(--critical)' }}>
        {error.message}
      </span>}
    </div>
  );
}
