import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, StatusPill, } from '../components/ui.jsx';
import { Donut, RingLegend, RingRow } from '../components/Ring.jsx';
import {
  getPlan, money, monthLabel, simulateSpend, undoDraw,
} from '../api.js';

/**
 * Allowance: what is left to spend this week, as a ring with its parts beside
 * it — the week's share, what rolled over, and what has gone.
 */
export default function TodayPanel({ month, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // `version` is in the dependency list on purpose: it changes when a statement
  // is imported, and the plan has to be recomputed against the new ledger even
  // though the month it is showing hasn't changed.
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getPlan(month));
    } catch (e) {
      setError(e);
    }
  }, [month, version]);

  useEffect(() => { load(); }, [load]);

  if (!data && !error) return <Loading what="your allowance" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const { state, status, banks, draws } = data;
  const thisMonth = new Date().toISOString().slice(0, 7);
  // A month that has already ended is a different question — "what was
  // left on the last day" rather than "what can I spend now" — and the panel
  // has to say which one it is answering.
  const live = state.month === thisMonth;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      <SafeToSpend state={state} live={live} />
      <ThisMonth status={status} state={state} live={live}
                 total={data.spent_in_total} fromBanks={data.from_banks} />
      <CanIBuyThis month={state.month} />

      <PiggyBanks banks={banks} draws={draws}
                  allocated={data.allocated_this_month} onTab={onTab}
                  onChanged={load} />
    </div>
  );
}

/** "Oct 5–11", or "Oct 31" for a one-day week. */
function weekDates(month, week) {
  const [y, m] = month.split('-').map(Number);
  const mon = new Date(y, m - 1, 1).toLocaleString('en', { month: 'short' });
  return week.first_day === week.last_day
    ? `${mon} ${week.first_day}`
    : `${mon} ${week.first_day}–${week.last_day}`;
}

/* ── The number ──────────────────────────────────────────────────────────── */

function SafeToSpend({ state, live }) {
  // What is left of this week, as a ring: the week's money all the way round,
  // what has been spent drawn on it. A shortfall from earlier in the month is
  // spread over the weeks that remain rather than dumped on this one.
  const week = state.week;
  const left = week.left;
  const over = left < 0;
  const behind = week.behind;
  const spent = Math.max(week.spent, 0);
  const pot = Math.max(left + week.spent, 0);
  const spentColor = over ? 'var(--critical)' : 'var(--ring-1)';

  return (
    <Card className={`hero-card${over ? ' behind' : ''}`}>
      <div className="ring-head">
        <h2>
          {live ? 'This week'
                : `Last week of ${monthLabel(state.month, { long: true })}`}
          <span className="week-dates"> · {weekDates(state.month, week)}</span>
        </h2>
        {over ? (
          <StatusPill state="critical">Over by {money(-left, { cents: true })}</StatusPill>
        ) : behind ? (
          <StatusPill state="warning">Catching up</StatusPill>
        ) : null}
      </div>
      <RingRow>
        <Donut size={168} thickness={15} total={over ? spent : pot}
               segments={[{ label: 'Spent', value: spent, color: spentColor,
                            title: money(spent, { cents: true }) }]}
               label={`${money(left, { cents: true })} left of ${
                 money(pot, { cents: true })} this week`}>
          <div className={`big num${over ? ' bad' : ''}`}>{money(Math.abs(left))}</div>
          <div className="under">{over ? 'Over' : 'Left'}</div>
        </Donut>
        <RingLegend items={behind ? [
          { label: "This week's budget", value: money(pot, { cents: true }), icon: 'flag' },
          { label: 'Spent', value: money(week.spent, { cents: true }), icon: 'bag',
            color: spentColor },
        ] : [
          { label: 'Weekly allowance', value: money(week.share, { cents: true }),
            icon: 'flag' },
          { label: 'Rolled over', value: money(week.carried_in, { cents: true }),
            icon: 'plus', color: 'var(--ring-3)' },
          { label: 'Spent', value: money(week.spent, { cents: true }), icon: 'bag',
            color: spentColor },
        ]} />
      </RingRow>
      <div className="ring-foot">
        {live && !over && week.days_left > 1 && (
          <><strong className="num">{money(week.per_day, { cents: true })}</strong> a day · </>
        )}
        {state.remaining < 0
          ? `${money(-state.remaining, { cents: true })} past the month's ${money(state.budget)}`
          : `${money(state.remaining, { cents: true })} left this month`}
      </div>
    </Card>
  );
}

/* ── How are you doing this month ────────────────────────────────────────── */

function ThisMonth({ status, state, live, total, fromBanks }) {
  const budget = Math.max(state.budget ?? 0, 0);
  const spent = Math.max(status.spent, 0);
  const over = spent > budget;
  const used = budget > 0 ? spent / budget : 0;
  const lands = status.projected_over > 0;

  return (
    <Card title={live
            ? monthLabel(state.month, { full: true })
            : `How ${monthLabel(state.month, { long: true })} went`}
          actions={<StatusPill state={status.tone}>{status.verdict}</StatusPill>}>
      <RingRow>
        <Donut size={140} thickness={13} total={over ? spent : budget}
               marker={live && budget > 0
                 ? Math.min(status.expected_by_now / budget, 1) : null}
               segments={[{ label: 'Spent', value: spent,
                            color: over ? 'var(--critical)' : 'var(--ring-1)',
                            title: money(spent, { cents: true }) }]}
               label={`${Math.round(used * 100)}% of ${money(budget)} spent`}>
          <div className={`small-big num${over ? ' bad' : ''}`}>
            {Math.round(used * 100)}%
          </div>
          <div className="under">of {money(budget)}</div>
        </Donut>
        <RingLegend items={[
          { label: 'Spent', value: money(status.spent, { cents: true }),
            color: over ? 'var(--critical)' : 'var(--ring-1)' },
          live && { label: 'On pace by today', value: money(status.expected_by_now),
                    icon: 'tick' },
          { label: 'Lands at', value: money(status.projected_month_end),
            tone: lands ? 'bad' : 'good', icon: 'trend',
            color: lands ? 'var(--critical)' : 'var(--good-text)' },
          { label: 'Monthly allowance', value: `${money(state.monthly_amount)}/mo`,
            icon: 'flag' },
        ]} />
      </RingRow>
      {state.remaining >= 0 && state.days_left > 1 && (
        <div className="ring-foot">
          <strong className="num">{money(state.spread_daily, { cents: true })}</strong> a day
          for the {state.days_left} days left
        </div>
      )}
      {total != null && (
        <div className="ring-foot total-line">
          <strong className="num">{money(total, { cents: true })}</strong> spent in total
          {live ? ' this month' : ` in ${monthLabel(state.month, { long: true })}`}
          {fromBanks > 0 && (
            <> · <strong className="num">{money(fromBanks, { cents: true })}</strong> from piggy banks</>
          )}
        </div>
      )}
    </Card>
  );
}

/* ── Can I buy this ─────────────────────────────────────────────────────── */

function CanIBuyThis({ month }) {
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

  return (
    <Card title="Thinking about buying something?">
      <form className="controls" onSubmit={ask}>
        <label htmlFor="ask-amount">It costs</label>
        <input id="ask-amount" type="number" min="0.01" step="0.01" required
               value={amount} onChange={(e) => setAmount(e.target.value)}
               placeholder="0.00" style={{ width: 130 }} />
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Checking…' : 'Can I?'}
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
              {result.affordable ? 'Yes' : 'Not out of this week'}
            </StatusPill>
            <span>{result.message}</span>
          </div>

          {result.options.length > 0 && (
            <>
              <div className="tile-label" style={{ marginTop: 16 }}>
                If you buy it
              </div>
              <div className="options">
                {result.options.map((o, i) => (
                  <div key={i} className={`option${o.viable ? '' : ' unviable'}`}>
                    <div>
                      <div className="ol">{o.label}</div>
                      <div className="od">{o.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/* ── Piggy banks, as seen from here ─────────────────────────────────────── */

/**
 * Read-only on purpose. Piggy banks are opened and edited on their own tab,
 * and a second form here that could change a target would be a second place
 * deciding the same number.
 */
function PiggyBanks({ banks, draws, allocated, onTab, onChanged }) {
  const [undoing, setUndoing] = useState(null);

  async function undo(id) {
    setUndoing(id);
    try {
      await undoDraw(id);
      await onChanged?.();
    } finally {
      setUndoing(null);
    }
  }

  return (
    <Card title="Piggy banks">
      {banks.length === 0 ? (
        onTab && (
          <button className="btn" onClick={() => onTab('piggy')}>Open a piggy bank</button>
        )
      ) : (
        <div className="bars" style={{ marginBottom: 14 }}>
          {banks.map((b) => (
            <div className="bucket" key={b.id}>
              <div className="name with-ring">
                <Donut size={36} thickness={5} total={1}
                       segments={[{ label: b.name,
                                    value: b.available < 0 ? 1 : (b.funded_share ?? 0),
                                    color: b.available < 0
                                      ? 'var(--critical)' : 'var(--ring-3)' }]}
                       label={`${b.name}: ${Math.round((b.funded_share ?? 0) * 100)}% full`} />
                <div>
                  {b.name}
                  <div className="desc">
                    {b.categories?.length ? `Pays for ${b.categories.join(', ')} · ` : ''}
                    {money(b.monthly)} a month
                  </div>
                </div>
              </div>
              <div className="num val">
                {b.available < 0
                  ? `${money(-b.available, { cents: true })} over`
                  : `${money(b.available, { cents: true })} left`}
              </div>
            </div>
          ))}
        </div>
      )}

      {allocated > 0 && (
        <p className="small" style={{ margin: '0 0 12px' }}>
          <strong>{money(allocated, { cents: true })}</strong> paid by piggy banks
          this month
        </p>
      )}

      {draws?.length > 0 && (
        <table>
          <thead>
            <tr><th>Borrowed</th><th className="r">Amount</th><th /></tr>
          </thead>
          <tbody>
            {draws.map((d) => (
              <tr key={d.id}>
                <td>
                  {d.name}
                  <span className="muted small"> · {monthLabel(d.month)}</span>
                </td>
                <td className="r num">{money(d.amount, { cents: true })}</td>
                <td className="r">
                  <button className="btn quiet" disabled={undoing === d.id}
                          onClick={() => undo(d.id)}>
                    {undoing === d.id ? 'Undoing…' : 'Undo'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {onTab && banks.length > 0 && (
        <button className="btn quiet" style={{ marginTop: 14 }}
                onClick={() => onTab('piggy')}>
          Manage piggy banks
        </button>
      )}
    </Card>
  );
}
