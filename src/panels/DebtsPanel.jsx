import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getDebts, putDebtDetails } from '../api.js';
import { DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Field } from './GoalsParts.jsx';
import { MONTH_NAMES, shown } from './HomePanel.jsx';
import { GrowthTabs } from './InsightsParts.jsx';
import './home.css';

/**
 * Debts (THL-49, designed in THL-128): D-01 the card on Home, D-02 every
 * debt under Growth, D-03 adding a rate and minimum the bank doesn't share.
 *
 * Carried balances sit beside safe-to-spend and are never taken out of it;
 * minimum payments are bills (D1, D2). A card's balance is split into what
 * was carried from before Pearl, anything carried from last month, and this
 * month's purchases, which already count as spending (D3). Only carried
 * balances are debts, and there's no "add a debt" (D4). Calm copy: what she
 * owes and what's due, no alarm words, nothing in red.
 */

const KIND_WORDS = { card: 'Credit card', line_of_credit: 'Line of credit', student_loan: 'Loan',
                     mortgage: 'Mortgage', loan: 'Loan' };
const isCard = (d) => d.kind === 'card' || d.kind === 'line_of_credit';
const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const ordinal = (n) => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
/** "October 22" from "2026-10-22". */
const monthDay = (iso) => `${MONTH_NAMES[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

/** What D-02 says about one debt. */
export function debtLines(d) {
  const minimum = d.minimum
    ? isCard(d)
      ? `minimum ${shown(d.minimum)}${d.due_date ? ` due ${monthDay(d.due_date)}` : ' a month'}`
      : `minimum ${shown(d.minimum)} a month${d.due_day ? `, due on the ${ordinal(d.due_day)}` : ''}`
    : null;
  const first = [d.rate !== null && d.rate !== undefined ? `${d.rate}% interest` : null, minimum]
    .filter(Boolean).join(' · ');
  let second;
  if (isCard(d)) {
    const since = d.carried - (d.before_pearl ?? 0);
    second = [
      d.before_pearl >= 1 ? `${shown(d.before_pearl)} from before Pearl` : null,
      since >= 1 ? `${shown(since)} carried from last month` : null,
      d.new_this_month >= 1 ? `${shown(d.new_this_month)} new this month, already counted as spending` : null,
    ].filter(Boolean).join(' · ');
  }
  const missing = [];
  if (d.rate === null || d.rate === undefined) {
    missing.push(isCard(d) ? 'Your bank doesn’t share the interest rate.' : 'Your lender doesn’t share the interest rate.');
  }
  if (!d.minimum) missing.push('Add the minimum payment and we’ll count it with your bills.');
  const action = d.rate == null && !d.minimum ? 'Add the details'
    : d.rate == null ? 'Add the rate' : !d.minimum ? 'Add the minimum' : 'Change the details';
  return { first: first ? capital(first) : null, second: second || null, missing, action,
           kind: KIND_WORDS[d.kind] ?? 'Loan' };
}

/** D-01: on Home only when she has a debt. */
export function DebtsCard({ debts, onSee }) {
  if (!debts?.count) return null;
  const total = debts.count === 1 ? `${shown(debts.total)} owed.` : `${shown(debts.total)} across ${debts.count}.`;
  return (
    <section className="hm-card hm-debts" aria-labelledby="hm-debts-title">
      <div className="hm-row-between">
        <h2 className="pk-h3" id="hm-debts-title">Debts</h2>
        <button type="button" className="hm-link" onClick={onSee}>
          See debts <PIcon name="chevronRight" size={14} />
        </button>
      </div>
      <p className="pk-muted">{`${total} Balances aren’t taken out of safe-to-spend.`}</p>
      <dl className="hm-facts">
        {debts.debts.slice(0, 3).map((d) => (
          <div key={d.account_id}><dt>{d.name}</dt><dd>{shown(d.balance)}</dd></div>
        ))}
      </dl>
    </section>
  );
}

export default function DebtsPanel({ onTab, onChanged, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getDebts().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your debts…</p></div>;
  const debt = editing && data.debts.find((d) => d.account_id === editing);
  return (
    <DebtsPage data={data} onEdit={setEditing} onTab={onTab}>
      {debt && (
        <DetailsPanel debt={debt} onClose={() => setEditing(null)}
                      onSave={(fields) => putDebtDetails(debt.account_id, fields).then((next) => {
                        setData(next);
                        setEditing(null);
                        onChanged?.();
                      })} />
      )}
    </DebtsPage>
  );
}

/** D-02: every debt, the total and this month's minimums. */
export function DebtsPage({ data, onEdit, onTab, children = null }) {
  return (
    <div className="pk hm-page db-page">
      <header className="hm-head">
        <p className="pk-overline accent">Debts</p>
        <h1 className="pk-h1">Cash flow</h1>
      </header>
      <GrowthTabs current="debts" onTab={onTab} />
      <p className="pk-muted">
        Everything you owe, including balances from before Pearl. Balances aren’t taken out of
        safe-to-spend; minimum payments are counted as bills.
      </p>
      {data.count === 0 ? (
        <section className="hm-card">
          <h2 className="pk-h3">Nothing carried over</h2>
          <p className="pk-muted">
            No card balance carried from an earlier month and no loans on your linked accounts.
            Card purchases this month are counted as spending.
          </p>
        </section>
      ) : (
        <>
          <dl className="hm-facts db-summary">
            <div><dt className="db-total">Total owed</dt><dd className="db-total">{shown(data.total)}</dd></div>
            <div>
              <dt>Minimum payments this month</dt>
              <dd>{data.minimums ? shown(data.minimums) : 'Not added yet'}</dd>
            </div>
          </dl>
          {data.debts.map((d) => <DebtCard key={d.account_id} d={d} onEdit={() => onEdit(d.account_id)} />)}
        </>
      )}
      {children}
    </div>
  );
}

function DebtCard({ d, onEdit }) {
  const l = debtLines(d);
  const id = `db-${d.account_id}`;
  return (
    <section className="hm-card db-card" aria-labelledby={id}>
      <div className="hm-row-between db-head">
        <h2 className="pk-h3" id={id}>{d.name}</h2>
        <span className="db-balance">{shown(d.balance)}</span>
      </div>
      {l.first && <p>{l.first}</p>}
      {l.second && <p className="pk-muted pk-label">{l.second}</p>}
      {l.missing.map((m) => <p key={m} className="pk-muted pk-label">{m}</p>)}
      <span className="pk-pill db-kind">{l.kind}</span>
      <button type="button" className="hm-link" onClick={onEdit}>
        {l.action} <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** "5.7", "5.7%" → 5.7; "" → ""; anything else → NaN. */
export function parseNumber(text) {
  const clean = String(text ?? '').replace(/[$,%\s]|a month/g, '');
  if (clean === '') return '';
  return /^\d+(\.\d{1,2})?$/.test(clean) ? Number(clean) : NaN;
}

/** D-03: the rate, minimum and due day, from her statement. */
export function DetailsPanel({ debt, onClose, onSave }) {
  const [rate, setRate] = useState(debt.rate ?? '');
  const [minimum, setMinimum] = useState(debt.minimum ?? '');
  const [due, setDue] = useState(debt.due_day ?? '');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    const fields = { rate: parseNumber(rate), minimum: parseNumber(minimum), due_day: parseNumber(due) };
    if (Number.isNaN(fields.rate) || fields.rate > 100) { setError({ field: 'rate', text: 'Enter the interest rate as a percent, like 5.7.' }); return; }
    if (Number.isNaN(fields.minimum)) { setError({ field: 'minimum', text: 'Enter the minimum payment, like 120.' }); return; }
    if (Number.isNaN(fields.due_day) || (fields.due_day !== '' && !(Number.isInteger(fields.due_day) && fields.due_day >= 1 && fields.due_day <= 31))) {
      setError({ field: 'due_day', text: 'Enter the day of the month it’s due, from 1 to 31.' });
      return;
    }
    setError(null);
    setSaving(true);
    onSave(fields)
      .catch((err) => setError({ field: 'rate', text: err.message }))
      .finally(() => setSaving(false));
  };
  const has = debt.rate != null || debt.minimum;
  return (
    <DetailPanel label={has ? 'Change the details' : 'Add the details'} overline={debt.name} onClose={onClose}>
      <form className="hm-form" onSubmit={submit}>
        <h1 className="pk-h2">{has ? 'Change the details' : 'Add the details'}</h1>
        <p className="pk-muted">You’ll find these on your latest statement. You can change them any time.</p>
        <Field label="Interest rate" id="db-rate" error={error?.field === 'rate' ? error.text : null}>
          <input id="db-rate" inputMode="decimal" autoComplete="off" placeholder="5.7%"
                 value={rate} onChange={(e) => setRate(e.target.value)} />
        </Field>
        <Field label="Minimum payment a month" id="db-minimum" error={error?.field === 'minimum' ? error.text : null}>
          <input id="db-minimum" inputMode="decimal" autoComplete="off" placeholder="$120"
                 value={minimum} onChange={(e) => setMinimum(e.target.value)} />
        </Field>
        <Field label="Day of the month it’s due (optional)" id="db-due" error={error?.field === 'due_day' ? error.text : null}>
          <input id="db-due" inputMode="numeric" autoComplete="off" placeholder="28"
                 value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        <PButton type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</PButton>
      </form>
    </DetailPanel>
  );
}
