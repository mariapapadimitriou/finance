import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  addBill, addPay, answerRent, clearExpected, confirmBills, editBill, editPay, getIncomeBills,
  money, removeBill, saveExpected,
} from '../api.js';
import { ActionToast, Alert, DetailPanel, PButton, StatTile } from '../pearl/kit.jsx';
import IncomeBillsFlow, {
  BillForm, BillRow, ExpectedForm, PayForm, payMeta, rentWords, undoRemove,
} from '../pearl/IncomeBills.jsx';
import { ListRow, PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Income and bills (THL-45, THL-127): the pay and bills she
 * confirmed in the check after linking, to edit or add to — the same forms
 * as I-02, I-03 and I-05, in a side panel — and "Check again", which runs
 * I-01 to I-06 over the page. Replaces the prototype "Income and
 * commitments" page and its piggy banks (Goals › treasure chests have them).
 *
 * A bill's checkbox saves at once: ticked counts in "Bills still to come",
 * unticked doesn't. Removing a bill has no confirmation, only Undo.
 */

const whole = (n) => money(Math.round(n));

export default function IncomeBillsPanel({ onTab, onChanged, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [panel, setPanel] = useState(null);
  const [removed, setRemoved] = useState(null);
  const [checking, setChecking] = useState(false);
  const load = useCallback(() => {
    setError(null);
    return getIncomeBills().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  if (error && !data) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading your income and bills…</p></div>;

  // Every change moves Home's numbers, so the app reloads them too.
  const saved = (d) => { setData(d); setPanel(null); onChanged?.(); return d; };
  return (
    <IncomeBillsPage data={data} onTab={onTab} onOpen={setPanel}
                     onTick={(key, on) => confirmBills({ [key]: on }).then(saved).catch(setError)}
                     onRent={(q) => answerRent(q.key).then(saved).catch(setError)}
                     onCheck={() => setChecking(true)}>
      {panel?.kind === 'pay' && (
        <DetailPanel label={panel.pay ? 'Edit your pay' : 'Add income'} overline="Income"
                     onClose={() => setPanel(null)}>
          <PayForm pay={panel.pay} eyebrow={null} onCancel={() => setPanel(null)}
                   title={panel.pay ? 'Tell us about your pay' : 'Add another source of income'}
                   onSave={(f) => (panel.pay ? editPay(panel.pay.id, f) : addPay(f)).then(saved)} />
        </DetailPanel>
      )}
      {panel?.kind === 'expected' && (
        <DetailPanel label="Expected income" overline="Income" onClose={() => setPanel(null)}>
          <ExpectedForm expected={data.expected} eyebrow={null} title="What you expect each month"
                        sub={data.expected.estimate
                          ? `Pearl’s estimate is ${whole(data.expected.estimate)} a month, the average of your last 3 months. Your own amount is used instead until you clear it.`
                          : 'Tell us roughly what comes in after tax.'}
                        onSkip={() => setPanel(null)} skipLabel="Cancel"
                        onSave={(amount, varies) => saveExpected(amount, varies).then(saved)} />
          {data.expected.amount > 0 && (data.expected.estimate || data.pays.length > 0) && (
            <button type="button" className="hm-link"
                    onClick={() => clearExpected().then(saved).catch(setError)}>
              {data.expected.estimate ? `Use Pearl’s estimate (${whole(data.expected.estimate)})`
                : 'Use my pay instead'}
            </button>
          )}
        </DetailPanel>
      )}
      {panel?.kind === 'bill' && (
        <DetailPanel label={panel.bill ? 'Edit a bill' : 'Add a bill'} overline="Bills"
                     onClose={() => setPanel(null)}>
          <BillForm bill={panel.bill} eyebrow={null} onCancel={() => setPanel(null)}
                    onSave={(f) => (panel.bill ? editBill(panel.bill.key, f) : addBill(f)).then(saved)}
                    onRemove={() => removeBill(panel.bill.key).then((d) => {
                      saved(d);
                      setRemoved(d.removed);
                    }).catch(setError)} />
        </DetailPanel>
      )}
      {removed && (
        <ActionToast title={`${removed.name} removed`} detail="It no longer counts in your bills."
                     onUndo={() => {
                       const r = removed;
                       setRemoved(null);
                       undoRemove(r).then(saved).catch(setError);
                     }}
                     onDone={() => setRemoved(null)} />
      )}
      {checking && (
        <div className="ib-overlay" role="dialog" aria-modal="true" aria-label="Check your income and bills">
          <IncomeBillsFlow onDone={(d) => { setChecking(false); saved(d); }} />
        </div>
      )}
      {error && <p className="pk-muted" role="alert">{String(error.message ?? error)}</p>}
    </IncomeBillsPage>
  );
}

/** The page itself, from the check's payload. */
export function IncomeBillsPage({ data, onTab, onOpen, onTick, onRent, onCheck, children = null }) {
  const counted = data.bills.filter((b) => b.ticked);
  const others = data.bills.filter((b) => !b.ticked);
  const exp = data.expected;
  return (
    <div className="pk hm-page pf-page ib-page">
      <PageHead trail={[{ label: 'Profile', to: 'profile' }, { label: 'Income and bills' }]}
                title="Income and bills" onTab={onTab}>
        <p className="pk-muted">What comes in and the regular bills set aside before anything counts toward your Allowance.</p>
      </PageHead>

      <div className="pk-tiles">
        <StatTile label="Income each month" value={data.totals.income > 0 ? whole(data.totals.income) : 'Not set yet'} />
        <StatTile label="Regular bills" value={data.totals.bills > 0 ? whole(data.totals.bills) : 'None yet'} />
      </div>

      <section className="pf-section" aria-labelledby="ib-income">
        <h2 className="pk-h3" id="ib-income">Income</h2>
        <ul className="pf-list">
          {exp.amount > 0 && (
            <ListRow name="Your own amount"
                     sub={`${whole(exp.amount)} a month after tax${exp.varies ? ' · varies, so we plan carefully' : ' · used instead of Pearl’s estimate'}`}
                     end={<span className="pk-label ib-link">Edit</span>}
                     onOpen={() => onOpen({ kind: 'expected' })} />
          )}
          {data.pays.map((p) => (
            <ListRow key={p.id} name={p.name} sub={payMeta(p)}
                     end={<span className="pk-label ib-link">Edit</span>}
                     onOpen={() => onOpen({ kind: 'pay', pay: p })} />
          ))}
          {!data.pays.length && !(exp.amount > 0) && exp.estimate > 0 && (
            <ListRow name="Pearl’s estimate"
                     sub={`${whole(exp.estimate)} a month · the average of your last 3 months`}
                     end={<span className="pk-label ib-link">Use my own amount</span>}
                     onOpen={() => onOpen({ kind: 'expected' })} />
          )}
          {!data.pays.length && !(exp.amount > 0) && !(exp.estimate > 0) && (
            <ListRow name="No income confirmed yet" sub="Check again, or tell us what you expect"
                     onOpen={() => onOpen({ kind: 'expected' })} />
          )}
        </ul>
        <button type="button" className="hm-link" onClick={() => onOpen({ kind: 'pay', pay: null })}>
          + Add another source of income
        </button>
      </section>

      <section className="pf-section" aria-labelledby="ib-bills">
        <h2 className="pk-h3" id="ib-bills">Regular bills</h2>
        {data.rent_question && (
          <Alert action="Yes, it’s my rent" onAction={() => onRent(data.rent_question)}>
            {rentWords(data.rent_question)}
          </Alert>
        )}
        {counted.length === 0 && <p className="pk-muted">No regular bills counted yet.</p>}
        <div className="ib-list">
          {counted.map((b) => (
            <BillRow key={b.key} bill={b} ticked onTick={(on) => onTick(b.key, on)}
                     onEdit={() => onOpen({ kind: 'bill', bill: b })} />
          ))}
        </div>
        {others.length > 0 && (
          <>
            <p className="pk-overline">Not counted</p>
            <div className="ib-list">
              {others.map((b) => (
                <BillRow key={b.key} bill={b} ticked={false} onTick={(on) => onTick(b.key, on)}
                         onEdit={() => onOpen({ kind: 'bill', bill: b })} />
              ))}
            </div>
          </>
        )}
        <button type="button" className="hm-link" onClick={() => onOpen({ kind: 'bill', bill: null })}>
          + Add a bill we missed
        </button>
      </section>

      <section className="pf-section" aria-labelledby="ib-again">
        <h2 className="pk-h3" id="ib-again">Something changed?</h2>
        <p className="pk-muted">A new job, a new place, a bill that stopped. Run the check again with your latest transactions.</p>
        <PButton variant="secondary" className="ib-hug" onClick={onCheck}>Check again</PButton>
      </section>
      {children}
    </div>
  );
}
