import { useCallback, useEffect, useState } from 'react';
import Chart from '../components/Chart.jsx';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import { getProjections, money } from '../api.js';
import { projectionConfig } from '../charts.js';

/**
 * Projections: two lines, and the gap between them is the whole point.
 *
 * *Current pace* carries your own surplus forward. *With cuts* adds the savings
 * the engine has already found and priced. Neither is a forecast — they are
 * arithmetic on a trend, and the honest part is saying how thin that trend is,
 * so the months behind the numbers travel with them.
 */
export default function ProjectionsPanel({ insights, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState('');

  const load = useCallback(async (goal) => {
    setError(null);
    try {
      const d = await getProjections(goal || undefined);
      setData(d);
    } catch (e) {
      setError(e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);   // an import changes the spend history the projection rests on

  useEffect(() => { load(target); }, [load, target]);


  // Before the unavailable branch below, not after: on a failed load `data` is
  // null, so `!data?.available` was true and the page rendered an empty grey
  // notice under the error — a failure dressed as furniture.
  if (error && !data) return <ErrorNote error={error} onRetry={() => load(target)} />;
  if (!data) return <Loading what="projections" />;

  const foundAnnual = insights?.summary?.weighted_annual ?? 0;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={() => load(target)} />

      {/* Shown, not edited. Take-home pay had a Save button here and another on
          the Plan tab, both writing the same setting, and whichever was touched
          last won silently. One figure, one place to change it. */}
      <Card title="What this is built on"
            hint="All of it comes from the Plan tab">
        <p className="small" style={{ marginTop: 0, marginBottom: 12 }}>
          Take-home pay of{' '}
          <strong className="num">{money(data.monthly_income)}</strong> a month
          {data.basis?.from_plan && (
            <>, less {money(data.basis.fixed_total)} of commitments</>
          )}
          .{' '}
          {onTab
            ? <button className="link" onClick={() => onTab('plan')}>
                Change it on the Plan tab
              </button>
            : <>Change it on the Plan tab.</>}
        </p>
      </Card>

      {!data?.available ? (
        <Notice>
          {data?.reason}
          {data?.typical_monthly_spend > 0 && (
            <>
              {' '}Your typical month of spending across the imported cards is{' '}
              <strong>{money(data.typical_monthly_spend)}</strong>, from{' '}
              {data.months_observed} month
              {data.months_observed === 1 ? '' : 's'} of statements.
            </>
          )}
        </Notice>
      ) : (
        <>
          <Notice kind={data.from_plan ? undefined : 'error'}>
            {!data.from_plan && <strong>Read the surplus as a ceiling. </strong>}
            {data.caveat}
          </Notice>

          {data.from_plan ? (
            <>
              <div className="grid cols-3">
                <Tile label="You put away" value={money(data.basis.saving)}
                      note="the savings figure in your plan" tone="good" />
                <Tile label="Left unspent" value={money(data.basis.unspent)}
                      note={`${money(data.basis.leftover)} to spend, `
                            + `${money(data.basis.typical_spend)} typically spent`}
                      tone={data.basis.unspent < 0 ? 'bad' : 'good'} />
                <Tile label="Saved each month" value={money(data.monthly_surplus)}
                      note="what the two above come to"
                      tone={data.monthly_surplus < 0 ? 'bad' : 'good'} />
              </div>
              {data.basis.banks > 0 && (
                <p className="assumption">
                  Your piggy banks collect a further{' '}
                  <strong className="num">{money(data.basis.banks)}</strong> a
                  month, deliberately left out of the figures above. They do
                  accumulate, but they accumulate in order to be spent on the
                  thing they are named after, so counting them as savings would
                  overstate what you actually keep.
                </p>
              )}
              <div className="grid cols-2">
                <Tile label="Cuts found" value={money(data.monthly_cuts)}
                      note="a month, from the Savings tab" tone="good" />
                <Tile label="Typical spend" value={money(data.typical_monthly_spend)}
                      note={`median of ${data.months_observed} month`
                            + `${data.months_observed === 1 ? '' : 's'}, imported cards only`} />
              </div>
            </>
          ) : (
            <div className="grid cols-4">
              <Tile label="Take-home" value={money(data.monthly_income)} note="a month" />
              <Tile label="Typical spend" value={money(data.typical_monthly_spend)}
                    note="median month, imported cards only" />
              <Tile label="Surplus" value={money(data.monthly_surplus)}
                    note="take-home minus that spending"
                    tone={data.monthly_surplus < 0 ? 'bad' : 'good'} />
              <Tile label="Cuts found" value={money(data.monthly_cuts)}
                    note="a month, from the Savings tab" tone="good" />
            </div>
          )}

          <Card
            title="Twelve months out"
            hint="What following the plan accumulates, against what the last few months would"
            actions={<Confidence level={data.confidence}
                                 months={data.months_observed} />}
          >
            <div className="chart">
              <Chart
                config={projectionConfig(data.series)}
                ariaLabel={`Cumulative savings over twelve months: `
                  + `${money(data.at_12.pace)} at your recent pace, `
                  + `${money(data.at_12.on_plan)} following the plan`}
              />
            </div>
            <div className="legend" style={{ marginTop: 6 }}>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-1)' }} />
                Recent pace — {money(data.at_12.pace)} by month 12
              </span>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-3)' }} />
                Following the plan — {money(data.at_12.on_plan)} by month 12
              </span>
            </div>
            <p className="assumption" style={{ marginBottom: 0 }}>
              {/* Either line can be the higher one, and the honest reading
                  differs by which. Overspending the budget is the case the tab
                  used to project on its own and call the future. */}
              {data.at_12.on_plan >= data.at_12.pace ? (
                <>
                  Following the plan is worth{' '}
                  <strong className="num">
                    {money(data.at_12.on_plan - data.at_12.pace)}
                  </strong>{' '}
                  more over the year than the last few months would give you.
                  The plan line is simply what you have decided to put away —
                  it does not depend on your spending history, which is why it
                  is the one to aim at.
                </>
              ) : (
                <>
                  You are currently spending{' '}
                  <strong className="num">
                    {money(data.basis.leftover - data.plan_spend)}
                  </strong>{' '}
                  a month less than the plan allows, so your recent pace
                  accumulates{' '}
                  <strong className="num">
                    {money(data.at_12.pace - data.at_12.on_plan)}
                  </strong>{' '}
                  more over the year than the plan promises. Worth raising the
                  savings figure on the Plan tab by some of it — then it happens
                  on purpose rather than by accident.
                </>
              )}
              {data.monthly_cuts > 0 && (
                <> The {money(data.monthly_cuts)} a month of cuts on the Savings
                   tab would add to either line.</>
              )}
            </p>
          </Card>

          <Card title="How long until…"
                hint="A number you have in mind, under each scenario">
            <form className="controls" onSubmit={(e) => e.preventDefault()}>
              <label htmlFor="target">I want to save</label>
              <input id="target" type="number" min="0" step="any" value={target}
                     onChange={(e) => setTarget(e.target.value)}
                     placeholder="5,000" style={{ width: 140 }} />
            </form>

            {data.goal && (
              <div className="grid cols-2" style={{ marginTop: 16 }}>
                <Tile label="At your recent pace"
                      value={data.goal.pace_months
                        ? `${data.goal.pace_months} months`
                        : 'Never'}
                      note={data.goal.pace_months
                        ? `${money(data.monthly_surplus)} a month`
                        : 'this pace saves nothing'}
                      tone={data.goal.pace_months ? undefined : 'bad'} />
                <Tile label="Following the plan"
                      value={data.goal.plan_months
                        ? `${data.goal.plan_months} months`
                        : 'Never'}
                      note={data.monthly_on_plan !== null
                            && data.monthly_on_plan !== undefined
                        ? `${money(data.monthly_on_plan)} a month, your savings figure`
                        : `${money(data.monthly_surplus + data.monthly_cuts)} a month`}
                      tone={data.goal.plan_months ? 'good' : 'bad'} />
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, note, tone }) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className={`value num${tone ? ` ${tone}` : ''}`}>{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}

function Confidence({ level, months }) {
  const tone = { thin: 'warning', fair: 'warning', reasonable: 'good' }[level];
  return (
    <StatusPill state={tone}>
      {months} month{months === 1 ? '' : 's'} of data — {level} confidence
    </StatusPill>
  );
}
