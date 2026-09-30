import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import {
  coverFromBucket, deleteBucket, getPlan, money, monthLabel, setBucket,
  setPlanAmount, simulateSpend,
} from '../api.js';

/**
 * Today: one number, and the arithmetic behind it.
 *
 * The number itself is easy to show and easy to distrust, so every part of it is
 * on screen: the flat daily share, what rolled over from the days before, and
 * what today has already used. A safe-to-spend figure you can't reconstruct is
 * indistinguishable from one that was made up.
 */
export default function TodayPanel({ month, onMonth, version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

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

  if (!data && !error) return <Loading what="today's number" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const { state, status, buckets, draws, configured, suggested } = data;
  const thisMonth = new Date().toISOString().slice(0, 7);
  // Showing a month that has already ended is a different question — "what was
  // left on the last day" rather than "what can I spend now" — and the panel
  // has to say which one it is answering.
  const live = state.month === thisMonth;
  const latestWithData = data.months_with_data?.at(-1);

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      {!live && (
        <Notice>
          Nothing imported for {monthLabel(thisMonth, { long: true })} yet, so
          this is {monthLabel(state.month, { long: true })} — the most recent
          month you have statements for — as it finished. Import this month&apos;s
          statement and the number becomes about today.
          {onMonth && (
            <>
              {' '}
              <button className="btn quiet" onClick={() => onMonth(thisMonth)}>
                Show {monthLabel(thisMonth, { long: true })} anyway
              </button>
            </>
          )}
        </Notice>
      )}

      {live && !data.has_data_this_month && (
        <Notice>
          Nothing imported for {monthLabel(state.month, { long: true })} yet, so
          this reads as a month where nothing has been spent. The arithmetic below
          is real — it just has an empty month under it.
          {latestWithData && onMonth && (
            <>
              {' '}
              <button className="btn quiet" onClick={() => onMonth(latestWithData)}>
                Show {monthLabel(latestWithData, { long: true })} instead
              </button>
            </>
          )}
        </Notice>
      )}

      <SafeToSpend state={state} live={live} />
      <ThisMonth status={status} state={state} live={live} />
      <CanIBuyThis month={state.month} buckets={buckets} onCovered={load} />

      <div className="grid cols-2">
        <Buckets buckets={buckets} draws={draws} busy={busy} setBusy={setBusy}
                 onChanged={load} setError={setError} />
        <MonthlyAmount state={state} configured={configured} suggested={suggested}
                       onChanged={load} setError={setError} />
      </div>
    </div>
  );
}

const ordinal = (n) =>
  (n % 100 >= 11 && n % 100 <= 13) ? 'th'
    : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';

/* ── The number ──────────────────────────────────────────────────────────── */

function SafeToSpend({ state, live }) {
  const over = state.safe_today < 0;
  const carried = state.carried_in;

  return (
    <Card className={`hero-card${over ? ' behind' : ''}`}>
      <div className="safe">
        <div>
          <div className="tile-label">
            {live ? 'Safe to spend today'
                  : `Left on the last day of ${monthLabel(state.month)}`}
          </div>
          <div className={`figure num${over ? ' bad' : ''}`}>
            {money(state.safe_today, { cents: true })}
          </div>
          <div className="caption">
            Day {state.day} of {state.days_in_month} ·{' '}
            {state.days_left} day{state.days_left === 1 ? '' : 's'} left ·{' '}
            {state.remaining < 0
              ? `${money(-state.remaining, { cents: true })} past the ${money(state.budget)} budget`
              : `${money(state.remaining, { cents: true })} left of ${money(state.budget)}`}
          </div>
        </div>
        {over && (
          <StatusPill state="critical">
            Over by {money(-state.safe_today, { cents: true })}
          </StatusPill>
        )}
      </div>

      <div className="sum">
        <SumTerm label="Daily share" value={state.flat_daily}
                 note={`${money(state.budget)} ÷ ${state.days_in_month} days`} />
        <span className="op" aria-hidden="true">{carried < 0 ? '−' : '+'}</span>
        <SumTerm
          label={carried < 0 ? 'Owed from earlier days' : 'Rolled over'}
          value={Math.abs(carried)}
          note={carried < 0
            ? `the first ${state.day - 1} days went over`
            : `unspent across the first ${state.day - 1} days`}
          tone={carried < 0 ? 'bad' : 'good'}
        />
        <span className="op" aria-hidden="true">−</span>
        <SumTerm label={live ? 'Spent today' : 'Spent that day'}
                 value={state.spent_today}
                 note={`discretionary charges dated the ${state.day}${ordinal(state.day)}`} />
        <span className="op" aria-hidden="true">=</span>
        <SumTerm label={live ? 'Safe to spend' : 'What was left'}
                 value={state.safe_today} strong tone={over ? 'bad' : 'good'} />
      </div>

      {over && (
        <p className="assumption" style={{ marginBottom: 0 }}>
          {state.spread_daily >= 0 ? (
            <>
              Spread evenly instead, every remaining day gets{' '}
              <strong className="num">
                {money(state.spread_daily, { cents: true })}
              </strong>{' '}
              and the month still balances. Nothing is hidden — the daily number
              just drops.
            </>
          ) : (
            <>
              The month is{' '}
              <strong className="num">
                {money(-state.remaining, { cents: true })}
              </strong>{' '}
              past its budget, so spreading can&apos;t rescue it — there is
              nothing left to divide. Cover it from a bucket, or let it be a
              month that went over.
            </>
          )}
        </p>
      )}
      {state.covered > 0 && (
        <p className="assumption" style={{ marginBottom: 0 }}>
          Includes {money(state.covered, { cents: true })} drawn from your buckets
          this month.
        </p>
      )}
    </Card>
  );
}

function SumTerm({ label, value, note, strong = false, tone }) {
  return (
    <div className={`term${strong ? ' strong' : ''}`}>
      <div className="k">{label}</div>
      <div className={`v num${tone ? ` ${tone}` : ''}`}>
        {money(value, { cents: true })}
      </div>
      {note && <div className="n">{note}</div>}
    </div>
  );
}

/* ── How are you doing this month ────────────────────────────────────────── */

function ThisMonth({ status, state, live }) {
  const pace = state.pace;

  return (
    <Card title={live
            ? `How you're doing in ${monthLabel(state.month, { long: true })}`
            : `How ${monthLabel(state.month, { long: true })} went`}
          actions={<StatusPill state={status.tone}>{status.verdict}</StatusPill>}>
      <div className="grid cols-4">
        <Figure label="Spent so far" value={money(status.spent, { cents: true })}
                note={`${money(status.expected_by_now)} would be on pace`} />
        <Figure label="Pace" value={pace ? `${Math.round(pace * 100)}%` : '—'}
                note="of an even spend by today"
                tone={pace > 1.05 ? 'bad' : pace ? 'good' : undefined} />
        <Figure label="Lands at" value={money(status.projected_month_end)}
                note={status.projected_over > 0
                  ? `${money(status.projected_over)} over budget`
                  : `${money(-status.projected_over)} under budget`}
                tone={status.projected_over > 0 ? 'bad' : 'good'} />
        <Figure label={state.remaining < 0 ? 'Past budget by' : 'Left to spend'}
                value={money(Math.abs(state.remaining), { cents: true })}
                note={state.remaining < 0
                  ? 'nothing left to spread over the rest of the month'
                  : `${money(state.spread_daily, { cents: true })}/day from here`}
                tone={state.remaining < 0 ? 'bad' : undefined} />
      </div>

      {status.vs_baseline !== null && status.vs_baseline !== undefined && (
        <p className="assumption">
          Against your own median month, this one is heading{' '}
          <strong>{money(Math.abs(status.vs_baseline))}{' '}
            {status.vs_baseline > 0 ? 'higher' : 'lower'}</strong>.
        </p>
      )}
      <p className="assumption" style={{ marginBottom: 0 }}>
        Only discretionary spending counts here. Rent, utilities, insurance and
        card payments are already committed, and no amount of restraint on a
        Tuesday changes the hydro bill.
      </p>
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

function CanIBuyThis({ month, buckets, onCovered }) {
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
      await coverFromBucket(option.bucket_id, result.short_by, month);
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
    <Card title="Thinking about buying something?"
          hint="Enter the price and see whether today has room for it">
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
              {result.affordable ? 'Yes' : 'Not out of today'}
            </StatusPill>
            <span>{result.message}</span>
          </div>

          {result.options.length > 0 && (
            <>
              <div className="tile-label" style={{ marginTop: 16 }}>
                Two honest ways to do it anyway
              </div>
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
                        {o.viable ? 'Draw it' : 'Not enough in it'}
                      </button>
                    ) : (
                      <span className="pill">{o.viable ? 'Automatic' : 'Won\'t balance'}</span>
                    )}
                  </div>
                ))}
              </div>
              {buckets.length === 0 && (
                <p className="assumption" style={{ marginBottom: 0 }}>
                  Add a bucket below — Fun, Savings, whatever you keep aside — and
                  covering an overspend from it becomes an option here.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

/* ── Buckets ────────────────────────────────────────────────────────────── */

function Buckets({ buckets, draws, busy, setBusy, onChanged, setError }) {
  const [draft, setDraft] = useState({ name: '', balance: '' });

  async function add(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await setBucket(draft.name, Number(draft.balance || 0));
      setDraft({ name: '', balance: '' });
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(b) {
    const drawn = (draws ?? []).filter((d) => d.name === b.name);
    // Removing a bucket removes what was drawn from it, which raises this
    // month's budget back up. Worth saying out loud before it happens.
    if (drawn.length && !window.confirm(
      `"${b.name}" covered ${money(drawn.reduce((s, d) => s + d.amount, 0),
        { cents: true })} this month. Removing it takes that back out of the `
      + 'budget. Go ahead?'
    )) return;
    setBusy(true);
    try {
      await deleteBucket(b.id);
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Buckets" hint="Money set aside that an overspend can come out of">
      {buckets.length === 0 ? (
        <p className="small muted" style={{ marginTop: 0 }}>
          No buckets yet. A bucket is real money you already have somewhere —
          drawing on one reduces it, because the money has to come from
          somewhere.
        </p>
      ) : (
        <div className="bars" style={{ marginBottom: 14 }}>
          {buckets.map((b) => (
            <div className="bucket" key={b.id}>
              <div className="name">{b.name}</div>
              <div className="num val">{money(b.balance, { cents: true })}</div>
              <button className="btn quiet" disabled={busy}
                      onClick={() => remove(b)}>Remove</button>
            </div>
          ))}
        </div>
      )}

      <form className="controls" onSubmit={add}>
        <input type="text" value={draft.name} required placeholder="Fun, Savings…"
               aria-label="Bucket name" style={{ flex: '1 1 130px' }}
               onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <input type="number" min="0" step="0.01" value={draft.balance}
               placeholder="0.00" aria-label="Bucket balance" style={{ width: 110 }}
               onChange={(e) => setDraft({ ...draft, balance: e.target.value })} />
        <button className="btn" type="submit" disabled={busy}>Save</button>
      </form>

      {draws?.length > 0 && (
        <table style={{ marginTop: 16 }}>
          <thead>
            <tr><th>Drawn this month</th><th className="r">Amount</th></tr>
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

function MonthlyAmount({ state, configured, suggested, onChanged, setError }) {
  const [value, setValue] = useState(String(state.monthly_amount || ''));
  const [busy, setBusy] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await setPlanAmount(Number(value || 0));
      await onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Monthly spending plan"
          hint="The figure the daily number divides up">
      <form className="controls" onSubmit={save}>
        <label htmlFor="plan-amount">Each month I want to keep discretionary spending under</label>
        <input id="plan-amount" type="number" min="0" step="10" value={value}
               onChange={(e) => setValue(e.target.value)} style={{ width: 130 }} />
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>

      {!configured && suggested > 0 && (
        <p className="assumption">
          Using <strong>{money(suggested)}</strong> for now — your own median
          month of discretionary spending, so the daily number starts from what
          you actually do rather than a template. Set your own above and it
          stops guessing.
        </p>
      )}
      <p className="assumption" style={{ marginBottom: 0 }}>
        {money(state.monthly_amount)} ÷ {state.days_in_month} days ={' '}
        <strong className="num">{money(state.flat_daily, { cents: true })}</strong> a day.
      </p>
    </Card>
  );
}
