import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, Notice, StatusPill, } from '../components/ui.jsx';
import { Donut, RingLegend, RingRow } from '../components/Ring.jsx';
import {
  coverFromBank, getNudge, getPlan, getSetup, money, monthLabel,
  simulateSpend, skipSetupStep,
} from '../api.js';

/**
 * Allowance: what is left to spend this week, as a ring with its parts beside
 * it — the week's share, what rolled over, and what has gone.
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

  if (!data && !error) return <Loading what="your allowance" />;
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
      <ThisMonth status={status} state={state} live={live}
                 derivation={configured ? derivation : null}
                 total={data.spent_in_total} fromBanks={data.from_banks} />
      <CanIBuyThis month={state.month} banks={banks} onCovered={load}
                   onTab={onTab} />

      <PiggyBanks banks={banks} draws={draws}
                  allocated={data.allocated_this_month} onTab={onTab} />
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
        <h2>{live ? 'This week'
                  : `Last week of ${monthLabel(state.month, { long: true })}`}</h2>
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

function ThisMonth({ status, state, live, derivation, total, fromBanks }) {
  const budget = Math.max(state.budget ?? 0, 0);
  const spent = Math.max(status.spent, 0);
  const over = spent > budget;
  const used = budget > 0 ? spent / budget : 0;
  const lands = status.projected_over > 0;
  const d = derivation;

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
          { label: 'Weekly allowance', value: `${money(state.week.nominal)}/wk`,
            icon: 'flag' },
          d?.from_plan && { label: 'Essentials', value: `${money(d.essentials)}/mo`,
                            icon: 'calendar', color: 'var(--ring-4)' },
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
