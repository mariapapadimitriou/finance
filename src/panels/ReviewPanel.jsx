import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, MerchantMark } from '../components/ui.jsx';
import {
  INCOME_KINDS, dateLabel, dismissReview, excludeTransaction, getReview, linkPayback,
  money, monthLabel, setCategory, setIncomeType,
} from '../api.js';
import { NOT_SPENT, WhereDidThisGo } from './TransactionsPanel.jsx';

/**
 * Everything Pearl isn't sure about, in one place, each with its best guess
 * and why. Accepting a guess or choosing something else goes through the same
 * endpoints the rest of the app uses; "That's right" settles an item for good.
 */
export default function ReviewPanel({ categories, onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  const load = useCallback(async () => {
    try {
      setData(await getReview());
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => { load(); }, [load, reload]);

  async function act(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setReload((n) => n + 1);
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading what="what needs a look" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const spendable = categories.filter((c) => !NOT_SPENT.has(c.name)).map((c) => c.name);
  const empty = data.count === 0;
  const exclude = (txn) => {
    const reason = window.prompt(`Leave out ${txn.merchant} ${money(txn.amount, { cents: true })}? Why?`);
    if (reason && reason.trim()) act(() => excludeTransaction(txn.id, reason.trim()));
  };
  const dismiss = (key) => act(() => dismissReview(key));

  return (
    <div className="stack">
      <ErrorNote error={error} />
      {empty && (
        <Card>
          <p className="review-empty">Nothing to review.</p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <button className="btn" onClick={() => onTab?.('transactions')}>See all transactions</button>
          </div>
        </Card>
      )}

      <WhereDidThisGo categories={categories} reload={reload}
                      onDone={() => { setReload((n) => n + 1); onChanged?.(); }} />

      {data.money_in.length > 0 && (
        <Card title="Money in" className="review-card">
          <ul className="review-list">
            {data.money_in.map((it) => (
              <MoneyIn key={it.key} it={it} busy={busy}
                       onPayback={(charge) => act(() => linkPayback(charge.id, it.txn.id))}
                       onGift={() => act(() => setIncomeType(it.txn.id, 'gifts'))}
                       onLent={() => act(() => setCategory(it.txn.id, 'Lent'))}
                       onOwn={() => dismiss(it.key)}
                       onExclude={() => exclude(it.txn)} />
            ))}
          </ul>
        </Card>
      )}

      {data.unsure_category.length > 0 && (
        <Card title="Check the category" className="review-card">
          <ul className="review-list">
            {data.unsure_category.map((it) => (
              <Unsure key={it.key} it={it} busy={busy} categories={spendable}
                      onRight={() => dismiss(it.key)}
                      onPick={(cat, always) => act(() => setCategory(it.txn.id, cat, always))}
                      onExclude={() => exclude(it.txn)} />
            ))}
          </ul>
        </Card>
      )}

      {data.income_type.length > 0 && (
        <Card title="What kind of income?" className="review-card">
          <ul className="review-list">
            {data.income_type.map((it) => (
              <IncomeItem key={it.key} it={it} busy={busy}
                          onPick={(kind) => act(() => setIncomeType(it.txn.id, kind))}
                          onExclude={() => exclude(it.txn)} />
            ))}
          </ul>
        </Card>
      )}

      {data.three_pay_month.length > 0 && (
        <Card title="Paycheques" className="review-card">
          <ul className="review-list">
            {data.three_pay_month.map((it) => (
              <li key={it.key} className="review-item">
                <div className="review-what">
                  <strong>{monthLabel(it.month, { full: true })} had three paycheques</strong>
                  <p className="muted small">{it.reason}
                    {it.monthly ? ` That’s ${money(it.monthly)}/mo from ${money(it.paycheque)} paycheques.` : ''}
                  </p>
                </div>
                <div className="review-actions">
                  <button className="btn" disabled={busy} onClick={() => dismiss(it.key)}>Got it</button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function What({ txn, reason }) {
  return (
    <div className="review-what">
      <div className="review-line">
        <MerchantMark logo={txn.logo} name={txn.merchant} />
        <strong>{txn.merchant}</strong>
        <span className={`num review-amt${txn.amount < 0 ? ' in' : ''}`}>
          {money(Math.abs(txn.amount), { cents: true })}
        </span>
      </div>
      <div className="muted small">{dateLabel(txn.date)} · {txn.account_name}</div>
      <p className="review-reason small">{reason}</p>
    </div>
  );
}

function MoneyIn({ it, busy, onPayback, onGift, onLent, onOwn, onExclude }) {
  const [charge, setCharge] = useState(it.guess.charge?.id ?? '');
  const chosen = it.candidates.find((c) => c.id === charge);
  return (
    <li className="review-item">
      <What txn={it.txn} reason={it.reason} />
      <div className="review-actions">
        {it.candidates.length > 0 && (
          <>
            {it.candidates.length > 1 && (
              <select aria-label="Which charge it paid back" value={charge}
                      onChange={(e) => setCharge(e.target.value)}>
                {it.candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.merchant} {money(c.amount)} · {dateLabel(c.date)} (1/{c.split})
                  </option>
                ))}
              </select>
            )}
            <button className="btn primary" disabled={busy || !chosen}
                    onClick={() => onPayback(chosen)}>
              Paid me back{it.candidates.length === 1 && chosen ? ` · ${chosen.merchant}` : ''}
            </button>
          </>
        )}
        <button className={`btn${it.candidates.length ? '' : ' primary'}`} disabled={busy}
                onClick={onOwn}>My own money</button>
        <button className="btn" disabled={busy} onClick={onGift}>A gift</button>
        <button className="btn" disabled={busy} onClick={onLent}>Paid back a loan</button>
        <button className="btn quiet" disabled={busy} onClick={onExclude}>Exclude…</button>
      </div>
    </li>
  );
}

function Unsure({ it, busy, categories, onRight, onPick, onExclude }) {
  const [always, setAlways] = useState(true);
  return (
    <li className="review-item">
      <What txn={it.txn} reason={it.reason} />
      <div className="review-actions">
        {it.guess !== 'Other' && (
          <button className="btn primary" disabled={busy} onClick={onRight}>
            {it.guess} is right
          </button>
        )}
        <select aria-label={`Category for ${it.txn.merchant}`} value="" disabled={busy}
                onChange={(e) => e.target.value && onPick(e.target.value, always)}>
          <option value="">{it.guess === 'Other' ? 'Choose a category…' : 'Something else…'}</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="small muted review-always">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          Always for {it.txn.merchant}
        </label>
        <button className="btn quiet" disabled={busy} onClick={onExclude}>Exclude…</button>
      </div>
    </li>
  );
}

function IncomeItem({ it, busy, onPick, onExclude }) {
  return (
    <li className="review-item">
      <What txn={it.txn} reason={it.reason} />
      <div className="review-actions">
        <button className="btn primary" disabled={busy} onClick={() => onPick(it.guess)}>
          {it.guess_label} is right
        </button>
        <select aria-label={`Kind of income for ${it.txn.merchant}`} value="" disabled={busy}
                onChange={(e) => e.target.value && onPick(e.target.value)}>
          <option value="">Something else…</option>
          {Object.entries(INCOME_KINDS).filter(([k]) => k !== it.guess)
            .map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <button className="btn quiet" disabled={busy} onClick={onExclude}>Exclude…</button>
      </div>
    </li>
  );
}
