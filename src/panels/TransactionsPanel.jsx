import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import {
  addTransaction, allocateToBank, dateLabel, deleteTransaction, getBanks,
  getTransactions, money, setCategory, unallocate,
} from '../api.js';

const PAGE = 100;

const today = () => new Date().toISOString().slice(0, 10);

export default function TransactionsPanel({ summary, categories, accounts, onChanged }) {
  const [filters, setFilters] = useState({ month: '', category: '', account: '', q: '' });
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [charging, setCharging] = useState(null);
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
            {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>

          <label htmlFor="f-acct">Card</label>
          <select id="f-acct" value={filters.account} onChange={(e) => update('account', e.target.value)}>
            <option value="">All</option>
            {accounts.map((a) => (
              <option key={a.account_id} value={a.account_id}>{a.account_name}</option>
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
        hint="Click a category to correct it — corrections can apply to every charge from that merchant"
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
                    <th className="r">Amount</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id}>
                      <td className="muted">{dateLabel(t.date)}</td>
                      <td className="merchant">
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
                          </button>
                        )}
                      </td>
                      <td className="muted">{t.account_name}</td>
                      <td>
                        <BankCell
                          txn={t} banks={banks}
                          open={charging === t.id}
                          onOpen={() => setCharging(charging === t.id ? null : t.id)}
                          onDone={() => { setCharging(null); bump(); }}
                        />
                      </td>
                      <td className="r" style={t.amount < 0 ? { color: 'var(--good-text)' } : undefined}>
                        {money(t.amount, { cents: true })}
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
        <span className="muted small">
          For cash, or a charge that hasn&apos;t posted yet
        </span>
      </div>
    );
  }

  return (
    <Card title="Add a transaction by hand"
          hint="Checked against your ledger first, so the statement doesn't add it twice later"
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

      <p className="assumption">
        A positive amount is money out. Enter a refund as a negative number.
      </p>

      <ErrorNote error={error} />

      {added && (
        <Notice kind="good">
          Added, filed under <strong>{added.category}</strong> as{' '}
          <strong>{added.merchant}</strong>.
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

/**
 * Charging one transaction to a piggy bank, or putting it back.
 *
 * This is the gesture that makes piggy banks worth having. A charge allocated
 * to a bank leaves the month it fell in — it is not in the Overview, the
 * budgets, or the daily number — because it was already paid for over the
 * months leading up to it. Putting it back is one click, and the month gets it
 * again.
 *
 * Only outflows can be charged: a refund or a card payment is money coming
 * back, and there is nothing to take out of a bank.
 */
function BankCell({ txn, banks, open, onOpen, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const bank = banks.find((b) => b.id === txn.bank_id);

  async function charge(id) {
    setBusy(true);
    setError(null);
    try {
      if (id) await allocateToBank(Number(id), txn.id);
      else await unallocate(txn.id);
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
              title={`Charged to ${bank.name} — not counted in this month`}>
        {bank.name} ✓
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
        <option value="">Count against this month</option>
        {banks.map((b) => (
          <option key={b.id} value={b.id}>{b.name}</option>
        ))}
      </select>
      <button className="btn quiet" onClick={onOpen} disabled={busy}>Close</button>
      {error && <span className="small" style={{ color: 'var(--critical)' }}>
        {error.message}
      </span>}
    </div>
  );
}
