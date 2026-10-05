import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, GoTo, Loading, Notice, StatusPill, } from '../components/ui.jsx';
import {
  coverFromBank, getNudge, getPlan, getSetup, money, monthLabel,
  simulateSpend, skipSetupStep,
} from '../api.js';

/**
 * Today: one number, and the arithmetic behind it.
 *
 * The number itself is easy to show and easy to distrust, so every part of it is
 * on screen: the flat daily share, what rolled over from the days before, and
 * what today has already used. A safe-to-spend figure you can't reconstruct is
 * indistinguishable from one that was made up.
 */
export default function TodayPanel({ month, onMonth, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [nudge, setNudge] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [setup, setSetup] = useState(null);

  // `version` is in the dependency list on purpose: it changes when a statement
  // is imported, and the plan has to be recomputed against the new ledger even
  // though the month it is showing hasn't changed.
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getPlan(month));
      // The server decides whether there is anything to say: it speaks only
      // about the current month, never on the 1st, and never about a day it
      // has no data for. Gating again here on which month is being *viewed*
      // silenced it entirely, because the panel falls back to the last month
      // with statements whenever this one is still empty.
      setNudge((await getNudge().catch(() => null))?.nudge ?? null);
      // Best effort: a checklist that fails to load is simply not shown,
      // rather than taking the weekly number down with it.
      setSetup(await getSetup().catch(() => null));
    } catch (e) {
      setError(e);
    }
  }, [month, version]);

  useEffect(() => { load(); }, [load]);

  if (!data && !error) return <Loading what="today's number" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const { state, status, banks, draws, configured, derivation } = data;
  const thisMonth = new Date().toISOString().slice(0, 7);
  // Showing a month that has already ended is a different question — "what was
  // left on the last day" rather than "what can I spend now" — and the panel
  // has to say which one it is answering.
  const live = state.month === thisMonth;
  const latestWithData = data.months_with_data?.at(-1);

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      {setup?.remaining > 0 && (
        <SetupChecklist setup={setup} onTab={onTab}
                        onSkip={async (id) => {
                          await skipSetupStep(id).catch(() => null);
                          setSetup(await getSetup().catch(() => null));
                        }} />
      )}

      {nudge && (
        <Notice kind={nudge.kind === 'over' ? 'error' : 'good'}>
          <strong>{nudge.headline}</strong> {nudge.detail}
        </Notice>
      )}

      {!live && (
        <Notice>
          Showing {monthLabel(state.month, { full: true })}
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
          Nothing yet for {monthLabel(state.month, { full: true })}
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
      <CanIBuyThis month={state.month} banks={banks} onCovered={load}
                   onTab={onTab} />

      <div className="grid cols-2">
        <PiggyBanks banks={banks} draws={draws}
                    allocated={data.allocated_this_month} onTab={onTab} />
        <MonthlyAmount state={state} configured={configured}
                       derivation={derivation} onTab={onTab} />
      </div>
    </div>
  );
}

/* ── What is left to set up ──────────────────────────────────────────────── */

/**
 * Only the steps not yet done, each a button to where it is done.
 *
 * Above the weekly number on purpose: until these are done the number is a
 * stand-in, and the list says what would make it real. Every tick comes from
 * the data rather than from pressing anything here, so a step done somewhere
 * else ticks itself, and the card disappears for good once the last one does.
 */
function SetupChecklist({ setup, onTab, onSkip }) {
  const todo = setup.steps.filter((s) => !s.done && !s.skipped);
  const done = setup.steps.filter((s) => s.done).length;
  const total = setup.steps.filter((s) => !s.skipped).length;

  return (
    <Card title="Finish setting up">
      <ol className="setup-steps">
        {todo.map((step) => (
          <li key={step.id}>
            <div className="what">
              <strong>{step.label}</strong>
            </div>
            <div className="row" style={{ gap: 6, flex: 'none' }}>
              {step.optional && (
                <button className="btn quiet" onClick={() => onSkip(step.id)}>
                  Skip
                </button>
              )}
              {onTab && (
                <button className="btn" onClick={() => onTab(step.tab)}>
                  {step.action}
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

const ordinal = (n) =>
  (n % 100 >= 11 && n % 100 <= 13) ? 'th'
    : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';

/* ── The number ──────────────────────────────────────────────────────────── */

function SafeToSpend({ state, live }) {
  // The number to act on: what is left of this week. A shortfall from earlier
  // in the month is spread over the weeks that remain rather than dumped on
  // this one, so the headline stays a figure you can use.
  const week = state.week;
  const left = week.left;
  const over = left < 0;
  const behind = week.behind;
  const carried = week.carried_in;
  const range = week.first_day === week.last_day
    ? `the ${week.first_day}${ordinal(week.first_day)}`
    : `the ${week.first_day}${ordinal(week.first_day)}–${week.last_day}${ordinal(week.last_day)}`;

  return (
    <Card className={`hero-card${over ? ' behind' : ''}`}>
      <div className="safe">
        <div>
          <div className="tile-label">
            {live ? 'Left this week'
                  : `Left in the last week of ${monthLabel(state.month, { long: true })}`}
          </div>
          <div className={`figure num${over ? ' bad' : ''}`}>
            {money(left, { cents: true })}
          </div>
          <div className="caption">
            {live && !over && week.days_left > 1 && (
              <>{money(week.per_day, { cents: true })} a day ·{' '}</>
            )}
            {state.remaining < 0
              ? `${money(-state.remaining, { cents: true })} past the ${money(state.budget)} budget`
              : `${money(state.remaining, { cents: true })} left this month`}
          </div>
        </div>
        {over ? (
          <StatusPill state="critical">
            Over by {money(-left, { cents: true })}
          </StatusPill>
        ) : behind ? (
          <StatusPill state="warning">Catching up</StatusPill>
        ) : null}
      </div>

      {/* The week's arithmetic, in the order it applies. */}
      <div className="sum">
        {behind ? (
          <>
            <SumTerm label="Left this month" value={state.remaining + week.spent}
                     note={`as the week began, on the ${week.first_day}${ordinal(week.first_day)}`} />
            <span className="op" aria-hidden="true">×</span>
            <SumTerm label="This week's days" value={`${week.days} of ${state.days_in_month - week.first_day + 1}`}
                     money={false} note="its share of what is left" />
          </>
        ) : (
          <>
            <SumTerm label="This week's share" value={week.share}
                     note={week.short
                       ? `${week.days} days (${range}) — a short week`
                       : `${week.days} days, ${range}`} />
            <span className="op" aria-hidden="true">+</span>
            <SumTerm label="Rolled over" value={carried}
                     note={week.first_day > 1
                       ? `unspent before the ${week.first_day}${ordinal(week.first_day)}`
                       : 'nothing yet — the month just started'}
                     tone="good" />
          </>
        )}
        <span className="op" aria-hidden="true">−</span>
        <SumTerm label={live ? 'Spent this week' : 'Spent that week'}
                 value={week.spent}
                 note="discretionary charges" />
        <span className="op" aria-hidden="true">=</span>
        <SumTerm label={live ? 'Left this week' : 'What was left'}
                 value={left}
                 tone={left < 0 ? 'bad' : 'good'} strong />
      </div>


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
                  : state.days_left <= 1
                    // On the last day there is nothing to spread it over, so
                    // "$755.38/day from here" advertised a daily allowance of
                    // $755 — arithmetically the remainder divided by one, and
                    // absurd as guidance.
                    ? 'all of it for the last day of the month'
                    : `${money(state.spread_daily, { cents: true })}/day over the `
                      + `${state.days_left} days left`}
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
function PiggyBanks({ banks, draws, allocated, onTab }) {
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
              <div className="name">
                {b.name}
                <div className="desc">
                  {b.categories?.length ? `Pays for ${b.categories.join(', ')} · ` : ''}
                  {money(b.monthly)} a month
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

      {onTab && banks.length > 0 && (
        <button className="btn quiet" style={{ marginTop: 14 }}
                onClick={() => onTab('piggy')}>
          Manage piggy banks
        </button>
      )}
    </Card>
  );
}

/* ── The monthly amount everything is measured against ──────────────────── */

function MonthlyAmount({ state, configured, derivation, onTab }) {
  const d = derivation ?? {};
  const planTab = <GoTo to="plan" from="today" onTab={onTab} />;

  return (
    <Card title="Where the weekly number comes from">
      {/* No input. The figure is derived from the plan on every request, so
          there is nothing here that could overwrite it and no stored copy to
          fall out of date. */}

      {configured && d.from_plan ? (
        <>
          {/* The chain in full. Showing only the last step is what made this
              tab look as though it disagreed with the Plan: "yours to spend"
              still has the groceries in it, and the weekly number deliberately
              does not. */}
          <div className="sum" style={{ marginBottom: 14 }}>
            <SumTerm label="Yours to spend" value={d.leftover}
                     note="from your plan" />
            <span className="op" aria-hidden="true">−</span>
            <SumTerm label="Essentials" value={d.essentials}
                     note={essentialsNote(d.essential_categories)} />
            <span className="op" aria-hidden="true">=</span>
            <SumTerm label="Day to day" value={d.discretionary} />
          </div>
          <div className="sum">
            <SumTerm label="Day to day" value={state.monthly_amount} />
            <span className="op" aria-hidden="true">÷</span>
            <SumTerm label="Days this month" value={state.days_in_month}
                     money={false} />
            <span className="op" aria-hidden="true">×</span>
            <SumTerm label="Days in a week" value={7} money={false} />
            <span className="op" aria-hidden="true">=</span>
            <SumTerm label="A week" value={state.week.nominal} strong
                     note={state.week.short
                       ? `this week is ${state.week.days} days, so it gets ${money(state.week.share)}`
                       : undefined} />
          </div>
        </>
      ) : (
        <>
          <div className="sum">
            <SumTerm label="Discretionary budget" value={state.monthly_amount}
                     note="a stand-in, from your own history" />
            <span className="op" aria-hidden="true">÷</span>
            <SumTerm label="Days this month" value={state.days_in_month}
                     money={false} />
            <span className="op" aria-hidden="true">×</span>
            <SumTerm label="Days in a week" value={7} money={false} />
            <span className="op" aria-hidden="true">=</span>
            <SumTerm label="A week" value={state.week.nominal} strong
                     note={state.week.short
                       ? `this week is ${state.week.days} days, so it gets ${money(state.week.share)}`
                       : undefined} />
          </div>
        </>
      )}
    </Card>
  );
}

/**
 * Name the categories that actually make up the essential half.
 *
 * Written out rather than illustrated with an example. The note used to say
 * "groceries, transport", and Transport is flagged discretionary — so it is in
 * the *other* column, and the one figure on this page whose whole purpose is to
 * be checkable was explained with a counter-example.
 */
function essentialsNote(categories) {
  const names = (categories ?? []).map((c) => c.toLowerCase());
  if (names.length === 0) return 'monthly';
  const shown = names.slice(0, 3).join(', ');
  const rest = names.length > 3 ? ` and ${names.length - 3} more` : '';
  return `${shown}${rest}`;
}
