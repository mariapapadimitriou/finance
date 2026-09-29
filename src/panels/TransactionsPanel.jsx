import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading } from '../components/ui.jsx';
import { dateLabel, getTransactions, money, setCategory } from '../api.js';

const PAGE = 100;

export default function TransactionsPanel({ summary, categories, accounts, onChanged }) {
  const [filters, setFilters] = useState({ month: '', category: '', account: '', q: '' });
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getTransactions({ ...filters, limit: PAGE, offset: page * PAGE })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e); });
    return () => { cancelled = true; };
  }, [filters, page]);

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
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Merchant</th>
                    <th>Category</th>
                    <th>Card</th>
                    <th className="r">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id}>
                      <td className="muted">{dateLabel(t.date)}</td>
                      <td className="merchant">
                        {t.merchant}
                        <div className="desc" title={t.description}>{t.description}</div>
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
                      <td className="r" style={t.amount < 0 ? { color: 'var(--good-text)' } : undefined}>
                        {money(t.amount, { cents: true })}
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
