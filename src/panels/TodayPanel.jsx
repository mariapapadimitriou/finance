import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import {
  coverFromBank, getNudge, getPlan, localMonth, money, monthLabel,
  simulateSpend,
} from '../api.js';

/**
 * Today: one number, with the arithmetic one click away.
 *
 * The headline and a single caption are what most visits need. The full
 * derivation — daily share, rollover, what today used, and where the monthly
 * figure comes from — sits behind "How is this calculated?" so it is always
 * checkable without being in the way.
 */
export default function TodayPanel({ month, onMonth, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [nudge, setNudge] = useState(null);
  const [error, setError] = useState(null);

  // `version` is in the dependency list on purpose: it changes when a statement
  // is imported, and the plan has to be recomputed against the new ledger even
  // though the month it is showing hasn't changed.
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getPlan(month));
      // The server decides whether there is anything to say: it speaks only
      // about the current month, never on the 1st, and never about a day it
      // has no data for.
      setNudge((await getNudge().catch(() => null))?.nudge ?? null);
    } catch (e) {
      setError(e);
    }
  }, [month, version]);

  useEffect(() => { load(); }, [load]);

  if (!data && !error) return <Loading what="today's number" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const { state, status, banks, draws, configured, derivation } = data;
  const thisMonth = localMonth();
  // Showing a month that has already ended answers "what was left on the last
  // day" rather than "what can I spend now", and the labels say which.
  const live = state.month === thisMonth;
  const latestWithData = data.months_with_data?.at(-1);
  const long = (m) => monthLabel(m, { long: true });

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      {nudge && (
        <Notice kind={nudge.kind === 'over' ? 'error' : 'good'}>
          <strong>{nudge.headline}</strong> {nudge.detail}
        </Notice>
      )}

      {!live && (
        <Notice>
          No {long(thisMonth)} data yet — showing {long(state.month)}.
          {onMonth && (
            <>{' '}
              <button className="link" onClick={() => onMonth(thisMonth)}>
                Show {long(thisMonth)}
              </button>
            </>
          )}
        </Notice>
      )}

      {live && !data.has_data_this_month && (
        <Notice>
          Nothing recorded for {long(state.month)} yet.
          {latestWithData && onMonth && (
            <>{' '}
              <button className="link" onClick={() => onMonth(latestWithData)}>
                Show {long(latestWithData)}
              </button>
            </>
          )}
        </Notice>
      )}

      <SafeToSpend state={state} live={live} configured={configured}
                   derivation={derivation} onTab={onTab} />
      <ThisMonth status={status} state={state} live={live} />
      <CanIBuyThis month={state.month} banks={banks} onCovered={load}
                   onTab={onTab} />
      <PiggyBanks banks={banks} draws={draws}
                  allocated={data.allocated_this_month} onTab={onTab} />
    </div>
  );
}

const ordinal = (n) =>
  (n % 100 >= 11 && n % 100 <= 13) ? 'th'
    : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';

/* ── The number ──────────────────────────────────────────────────────────── */

function SafeToSpend({ state, live, configured, derivation, onTab }) {
  // A shortfall is spread over the days that remain rather than dumped on
  // today, so the headline stays a figure you can use; the strict rollover is
  // in the breakdown.
  const headline = state.safe_today_effective ?? state.safe_today;
  const over = headline < 0;
  const recovering = state.recovering;
  const carried = state.carried_in;

  return (
    <Card className={`hero-card${over ? ' behind' : ''}`}>
      <div className="safe">
        <div>
          <div className="tile-label">
            {live ? 'Spend today'
                  : `Left on the last day of ${monthLabel(state.month)}`}
          </div>
          <div className={`figure num${over ? ' bad' : ''}`}>
            {money(headline, { cents: true })}
          </div>
          <div className="caption">
            {state.days_left} day{state.days_left === 1 ? '' : 's'} left ·{' '}
            {state.remaining < 0
              ? `${money(-state.remaining)} over the ${money(state.budget)} budget`
              : `${money(state.remaining)} left of ${money(state.budget)}`}
          </div>
        </div>
        {over ? (
          <StatusPill state="critical">Over</StatusPill>
        ) : recovering ? (
          <StatusPill state="warning">Catching up</StatusPill>
        ) : null}
      </div>

      {over && (
        <p className="assumption" style={{ marginBottom: 0 }}>
          {state.spread_daily >= 0
            ? <>Spread over the rest of the month:{' '}
                <strong className="num">{money(state.spread_daily, { cents: true })}</strong> a day.</>
            : 'Nothing left this month. Borrow from a piggy bank below, or let it go over.'}
        </p>
      )}
      {state.covered > 0 && (
        <p className="assumption" style={{ marginBottom: 0 }}>
          Includes {money(state.covered, { cents: true })} borrowed from piggy banks.
        </p>
      )}

      <details className="evidence" style={{ marginTop: 16 }}>
        <summary>How is this calculated?</summary>

        <div className="sum" style={{ marginTop: 12 }}>
          <SumTerm label="Daily share" value={state.flat_daily}
                   note={`${money(state.budget)} ÷ ${state.days_in_month} days`} />
          <span className="op" aria-hidden="true">{carried < 0 ? '−' : '+'}</span>
          <SumTerm
            label={carried < 0 ? 'Overspent earlier' : 'Rolled over'}
            value={Math.abs(carried)}
            note={`days 1–${Math.max(state.day - 1, 0)}`}
            tone={carried < 0 ? 'bad' : 'good'}
          />
          <span className="op" aria-hidden="true">−</span>
          <SumTerm label="Spent today" value={state.spent_today}
                   note={`the ${state.day}${ordinal(state.day)}`} />
          <span className="op" aria-hidden="true">=</span>
          <SumTerm label={recovering ? 'Strictly' : 'Today'}
                   value={state.safe_today}
                   tone={state.safe_today < 0 ? 'bad' : 'good'}
                   strong={!recovering} />
        </div>

        {recovering && (
          <div className="sum" style={{ marginTop: 10 }}>
            <SumTerm label="Left this month" value={state.remaining} />
            <span className="op" aria-hidden="true">÷</span>
            <SumTerm label="Days left" value={state.days_left} money={false} />
            <span className="op" aria-hidden="true">=</span>
            <SumTerm label="Spend today" value={headline} strong tone="good" />
          </div>
        )}

        <MonthlyAmount state={state} configured={configured}
                       derivation={derivation} onTab={onTab} />

        <p className="assumption" style={{ marginBottom: 0 }}>
          Only day-to-day spending counts. Bills and essentials are budgeted
          separately.
        </p>
      </details>
    </Card>
  );
}

function SumTerm({ label, value, note, strong = false, tone, money: asMoney = true }) {
  return (
    <div className={`term${strong ? ' strong' : ''}`}>
      <div className="k">{label}</div>
      <div className={`v num${tone ? ` ${tone}` : ''}`}>
        {asMoney ? money(value, { cents: true }) : value}
      </div>
      {note && <div className="n">{note}</div>}
    </div>
  );
}

/* ── How are you doing this month ────────────────────────────────────────── */

function ThisMonth({ status, state, live }) {
  return (
    <Card title={live ? 'This month' : monthLabel(state.month, { long: true })}
          actions={<StatusPill state={status.tone}>{status.verdict}</StatusPill>}>
      {/* Three short figures fit side by side even on a phone. */}
      <div className="grid" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
        <Figure label="Spent" value={money(status.spent)}
                note={`${money(status.expected_by_now)} would be on pace`} />
        <Figure label="On pace for" value={money(status.projected_month_end)}
                note={status.projected_over > 0
                  ? `${money(status.projected_over)} over`
                  : `${money(-status.projected_over)} under`}
                tone={status.projected_over > 0 ? 'bad' : 'good'} />
        <Figure label={state.remaining < 0 ? 'Over by' : 'Left'}
                value={money(Math.abs(state.remaining))}
                note={state.remaining < 0 || state.days_left <= 1
                  ? null
                  : `${money(state.spread_daily, { cents: true })}/day`}
                tone={state.remaining < 0 ? 'bad' : undefined} />
      </div>
    </Card>
  );
}

function Figure({ label, value, note, tone }) {
  return (
    <div className="figure-cell">
      <div className="tile-label">{label}</div>
      <div className={`fv num${tone ? ` ${tone}` : ''}`}>{value}</div>
      {note && <div className="fn">{note}</div>}
    </div>
  );
}

/* ── Can I buy this ─────────────────────────────────────────────────────── */

function CanIBuyThis({ month, banks, onCovered, onTab }) {
  const [amount, setAmount] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function ask(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await simulateSpend(Number(amount), month));
    } catch (err) {
      setError(err);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  async function cover(option) {
    setBusy(true);
    setError(null);
    try {
      await coverFromBank(option.bank_id, result.short_by, month);
      setResult(null);
      setAmount('');
      await onCovered();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Can I afford it?">
      <form className="controls" onSubmit={ask}>
        <label htmlFor="ask-amount">Price</label>
        <input id="ask-amount" type="number" min="0.01" step="0.01" required
               inputMode="decimal"
               value={amount} onChange={(e) => setAmount(e.target.value)}
               placeholder="0.00" style={{ width: 130 }} />
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Checking…' : 'Check'}
        </button>
        {result && (
          <button type="button" className="btn quiet"
                  onClick={() => { setResult(null); setAmount(''); }}>
            Clear
          </button>
        )}
      </form>

      <ErrorNote error={error} />

      {result && (
        <div className="verdict">
          <div className="line">
            <StatusPill state={result.affordable ? 'good' : 'warning'}>
              {result.affordable ? 'Yes' : "Over today's limit"}
            </StatusPill>
            <span>{result.message}</span>
          </div>

          {result.options.length > 0 && (
            <>
              <div className="tile-label" style={{ marginTop: 16 }}>Options</div>
              <div className="options">
                {result.options.map((o, i) => (
                  <div key={i} className={`option${o.viable ? '' : ' unviable'}`}>
                    <div>
                      <div className="ol">{o.label}</div>
                      <div className="od">{o.detail}</div>
                    </div>
                    {o.kind === 'cover' ? (
                      <button className="btn" disabled={!o.viable || busy}
                              onClick={() => cover(o)}>
                        {o.viable ? 'Borrow it' : 'Not enough in it'}
                      </button>
                    ) : (
                      <span className="pill">{o.viable ? 'Automatic' : "Won't balance"}</span>
                    )}
                  </div>
                ))}
              </div>
              {banks.length === 0 && onTab && (
                <p className="assumption" style={{ marginBottom: 0 }}>
                  <button className="link" onClick={() => onTab('piggy')}>
                    Open a piggy bank
                  </button>{' '}to borrow from it here.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/* ── Piggy banks, as seen from here ─────────────────────────────────────── */

/**
 * Read-only on purpose. Piggy banks are opened and edited on the Plan page,
 * and a second form here would be a second place deciding the same number.
 */
function PiggyBanks({ banks, draws, allocated, onTab }) {
  return (
    <Card title="Piggy banks"
          actions={onTab && banks.length > 0 && (
            <button className="btn quiet" onClick={() => onTab('piggy')}>
              Manage
            </button>
          )}>
      {banks.length === 0 ? (
        <p className="small muted" style={{ margin: 0 }}>
          Save monthly for yearly costs like trips or insurance.{' '}
          {onTab && (
            <button className="link" onClick={() => onTab('piggy')}>
              Open one
            </button>
          )}
        </p>
      ) : (
        <div className="bars">
          {banks.map((b) => (
            <div className="bucket" key={b.id}>
              <div className="name">
                {b.name}
                <div className="desc">{money(b.monthly)} a month</div>
              </div>
              <div className="num val">{money(b.balance, { cents: true })}</div>
            </div>
          ))}
        </div>
      )}

      {allocated > 0 && (
        <p className="small muted" style={{ margin: '14px 0 0' }}>
          {money(allocated, { cents: true })} of this month&apos;s spending is
          paid from piggy banks and isn&apos;t counted above.
        </p>
      )}

      {draws?.length > 0 && (
        <table style={{ marginTop: 14 }}>
          <thead>
            <tr><th>Borrowed this month</th><th className="r">Amount</th></tr>
          </thead>
          <tbody>
            {draws.map((d, i) => (
              <tr key={i}>
                <td>{d.name}</td>
                <td className="r num">{money(d.amount, { cents: true })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/* ── The monthly amount everything is measured against ──────────────────── */

function MonthlyAmount({ state, configured, derivation, onTab }) {
  const d = derivation ?? {};
  const planLink = onTab
    ? <button className="link" onClick={() => onTab('plan')}>Plan</button>
    : <strong>Plan</strong>;

  if (configured && d.from_plan) {
    return (
      <>
        <div className="sum" style={{ marginTop: 10 }}>
          <SumTerm label="Left after bills" value={d.leftover} note="from your Plan" />
          <span className="op" aria-hidden="true">−</span>
          <SumTerm label="Essentials" value={d.essentials}
                   note={essentialsNote(d.essential_categories)} />
          <span className="op" aria-hidden="true">=</span>
          <SumTerm label="Day-to-day" value={d.discretionary} />
        </div>
        <div className="sum" style={{ marginTop: 10 }}>
          <SumTerm label="Day-to-day" value={state.monthly_amount} />
          <span className="op" aria-hidden="true">÷</span>
          <SumTerm label="Days" value={state.days_in_month} money={false} />
          <span className="op" aria-hidden="true">=</span>
          <SumTerm label="Daily share" value={state.flat_daily} strong />
        </div>
        <p className="assumption" style={{ marginBottom: 0 }}>
          Change your income, bills or savings on the {planLink} and this
          updates.
        </p>
      </>
    );
  }

  return (
    <>
      <div className="sum" style={{ marginTop: 10 }}>
        <SumTerm label="Usual day-to-day" value={state.monthly_amount}
                 note="from your history" />
        <span className="op" aria-hidden="true">÷</span>
        <SumTerm label="Days" value={state.days_in_month} money={false} />
        <span className="op" aria-hidden="true">=</span>
        <SumTerm label="Daily share" value={state.flat_daily} strong />
      </div>
      <p className="assumption" style={{ marginBottom: 0 }}>
        Based on your usual spending. Add your income on the {planLink} to set
        it yourself.
      </p>
    </>
  );
}

/** The categories that make up the essential half, named rather than illustrated. */
function essentialsNote(categories) {
  const names = (categories ?? []).map((c) => c.toLowerCase());
  if (names.length === 0) return 'budgeted monthly';
  const shown = names.slice(0, 3).join(', ');
  const rest = names.length > 3 ? ` +${names.length - 3}` : '';
  return `${shown}${rest}`;
}
