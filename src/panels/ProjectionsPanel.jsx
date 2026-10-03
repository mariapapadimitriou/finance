import { useCallback, useEffect, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, StatusPill, Why,
} from '../components/ui.jsx';
import { destination } from '../nav.js';
import { getProjections, money, saveSavings } from '../api.js';
import { investedConfig, projectionConfig } from '../charts.js';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November',
                     'December'];

/**
 * Projections: two lines, and the gap between them is the whole point.
 *
 * *Current pace* carries your own surplus forward. *With cuts* adds the savings
 * the engine has already found and priced. Neither is a forecast — they are
 * arithmetic on a trend, and the honest part is saying how thin that trend is,
 * so the months behind the numbers travel with them.
 */
export default function ProjectionsPanel({ insights, onTab, onChanged,
                                          version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState('');
  // The slider's own position, and the figure the server has been asked to
  // project. Null in both means "whatever is saved" — dragging sets the
  // first immediately so the handle keeps up with the finger, and the second
  // follows a beat later so a drag is not one request per pixel.
  const [slider, setSlider] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (goal, savings) => {
    setError(null);
    try {
      // Not cleared first: on a re-fetch the previous figures stay on screen
      // rather than collapsing to a spinner under the slider being dragged.
      setData(await getProjections(goal || undefined, savings));
    } catch (e) {
      setError(e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);   // an import changes the spend history the projection rests on

  useEffect(() => {
    if (slider === null) return undefined;
    const id = setTimeout(() => setPreview(slider), 180);
    return () => clearTimeout(id);
  }, [slider]);

  useEffect(() => { load(target, preview ?? undefined); },
    [load, target, preview]);

  async function commit() {
    setSaving(true);
    setError(null);
    try {
      // The same endpoint and the same setting the plan's own field writes. One
      // figure with two editors is fine; two figures would not be.
      await saveSavings(slider);
      setSlider(null);
      setPreview(null);
      await load(target);
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }


  // Before the unavailable branch below, not after: on a failed load `data` is
  // null, so `!data?.available` was true and the page rendered an empty grey
  // notice under the error — a failure dressed as furniture.
  if (error && !data) return <ErrorNote error={error} onRetry={() => load(target)} />;
  if (!data) return <Loading what="projections" />;

  const foundAnnual = insights?.summary?.weighted_annual ?? 0;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={() => load(target)} />

      {/* Without a plan there is no slider to frame the figures, so this is
          the only place that says what they rest on. With one, the slider
          card says it in its first line and this card would be a repeat.
          Shown, not edited: take-home pay had a Save button here and another
          in the plan, and whichever was touched last won silently. */}
      {!data.basis?.from_plan && (
        <Card title="What this is built on">
          <p className="small" style={{ marginTop: 0, marginBottom: 0 }}>
            Take-home pay of{' '}
            <strong className="num">{money(data.monthly_income)}</strong> a
            month. Change it in{' '}
            <GoTo to="plan" from="projections" onTab={onTab} />.
          </p>
        </Card>
      )}

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
          {/* First: it is the one thing on the page you can move, and every
              figure below it moves with it. */}
          {data.from_plan && (
            <SavingsSlider
              onTab={onTab}
              data={data}
              value={slider ?? data.savings_saved ?? 0}
              onChange={setSlider}
              onCommit={commit}
              onReset={() => { setSlider(null); setPreview(null); }}
              saving={saving}
              dirty={slider !== null
                     && Math.abs(slider - (data.savings_saved ?? 0)) > 0.005}
            />
          )}

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
                <Why id="ahead.banks" label="Why aren't piggy banks counted?">
                  Your piggy banks collect a further{' '}
                  <strong className="num">{money(data.basis.banks)}</strong> a
                  month, deliberately left out of the figures above. They do
                  accumulate, but they accumulate in order to be spent on the
                  thing they are named after, so counting them as savings would
                  overstate what you actually keep.
                </Why>
              )}
              <div className="grid cols-2">
                <Tile label="Cuts found" value={money(data.monthly_cuts)}
                      note={`a month, from ${destination('savings', 'projections')}`} tone="good" />
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
                    note={`a month, from ${destination('savings', 'projections')}`} tone="good" />
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
                  savings figure above by some of it — then it happens on
                  purpose rather than by accident.
                </>
              )}
              {data.monthly_cuts > 0 && (
                <> The {money(data.monthly_cuts)} a month of cuts in{' '}
                   <GoTo to="savings" from="projections" onTab={onTab} /> would
                   add to either line.</>
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

          {data.invested && <Invested invested={data.invested} />}
        </>
      )}
    </div>
  );
}

/**
 * The savings figure, as something you can move and watch.
 *
 * Two things make this honest rather than a toy. The first is that nothing
 * here is computed in the browser: every figure comes back from the same
 * endpoint the saved value uses, asked a hypothetical question. The second is
 * that it shows the cost as well as the benefit — raising this does not
 * conjure money, it moves it out of what you may spend, and the tile for that
 * sits beside the two that go up.
 */
function SavingsSlider({ data, value, onChange, onCommit, onReset, saving,
                         dirty, onTab }) {
  const ceiling = Math.max(data.savings_ceiling ?? 0, value, 100);
  const max = Math.ceil(ceiling / 25) * 25;
  const filled = Math.round((value / max) * 100);
  const months = data.year_end?.months ?? 0;
  const from = MONTH_NAMES[12 - months] ?? '';

  return (
    <Card title="What if you put away more"
          hint="Drag it, and every figure below moves with it — nothing is saved until you say so"
          actions={dirty && (
            <div className="row" style={{ gap: 8 }}>
              <button className="btn quiet" onClick={onReset} disabled={saving}>
                Reset
              </button>
              <button className="btn primary" onClick={onCommit} disabled={saving}>
                {saving ? 'Saving…' : 'Make it the plan'}
              </button>
            </div>
          )}>
      <div className="controls" style={{ alignItems: 'center', gap: 14 }}>
        <label htmlFor="savings-slider" style={{ whiteSpace: 'nowrap' }}>
          Saving each month
        </label>
        <input
          id="savings-slider"
          className="measure"
          type="range"
          min="0"
          max={max}
          step="25"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{
            flex: '1 1 220px',
            minWidth: 160,
            // The filled part of the track, which Chromium will not draw.
            backgroundImage: `linear-gradient(to right, var(--brand) 0 ${
              filled}%, var(--surface-2) ${filled}% 100%)`,
          }}
          aria-valuetext={`${money(value)} a month`}
        />
        <strong className="num" style={{ fontSize: 20, minWidth: 96,
                                         textAlign: 'right' }}>
          {money(value)}
        </strong>
      </div>

      {/* What the figures rest on, in one line. It used to be a card of its
          own above this one, restating what the slider already frames. */}
      <p className="small muted" style={{ margin: '10px 0 0' }}>
        Out of{' '}
        <strong className="num">{money(data.basis?.income ?? data.monthly_income)}</strong>{' '}
        take-home, less{' '}
        <strong className="num">{money(data.basis?.fixed_total ?? 0)}</strong>{' '}
        of commitments — those are changed in{' '}
        <GoTo to="plan" from="projections" onTab={onTab} />.
      </p>

      <div className="grid cols-3" style={{ marginTop: 16 }}>
        <Tile label={`By 31 December`} value={money(data.year_end?.on_plan ?? 0)}
              note={months > 0
                ? `${months} more month${months === 1 ? '' : 's'}, ${from} on`
                : 'the year is done'}
              tone="good" />
        <Tile label="Over twelve months" value={money(data.at_12?.on_plan ?? 0)}
              note="following the plan" tone="good" />
        <Tile label="Left to spend" value={money(data.basis?.leftover ?? 0)}
              note="a month, after commitments and this"
              tone={(data.basis?.leftover ?? 0) <= 0 ? 'bad' : undefined} />
      </div>

      {/* Live state, so never folded away with the explanation below. */}
      {dirty && (
        <p className="small" style={{ margin: '14px 0 0' }}>
          Nothing is saved until you press <strong>Make it the plan</strong>.
        </p>
      )}

      {/* The thing a slider like this usually hides: it is not a tap that
          makes more money come out. The recent-pace line does not move at
          all, because what you actually accumulate is unchanged — what
          changes is how much of it was a decision. */}
      <Why id="ahead.slider" label="Does saving more mean I have more?">
        Not on its own. Moving this does not change what you accumulate, only
        how much of it happens on purpose: the money comes out of what is left
        to spend, and the recent-pace line below does not move. What it does
        change is the weekly number on Today, which divides the smaller
        leftover.
      </Why>
    </Card>
  );
}

/**
 * The same contribution, left to compound.
 *
 * Deliberately a range rather than a figure. One rate would be a forecast
 * wearing arithmetic's clothes; three make the point that the answer depends
 * on an assumption the app cannot make for her. Contributions are shown
 * against every value, because the gap is the only part that is news.
 */
function Invested({ invested }) {
  const chart = invested.rates.find((r) => r.rate === invested.chart_rate)
    ?? invested.rates[1] ?? invested.rates[0];
  const at30 = chart.at['30'];

  return (
    <Card title="If you invested it instead of holding it"
          hint={`${money(invested.monthly)} a month, compounded — assumptions, not predictions`}>
      <div className="chart">
        <Chart
          config={investedConfig(invested.series)}
          ariaLabel={`Invested at ${Math.round(invested.chart_rate * 100)}% a `
            + `year, ${money(invested.monthly)} a month grows to `
            + `${money(at30.value)} over thirty years, of which `
            + `${money(at30.contributed)} is what you put in`}
        />
      </div>
      <div className="legend" style={{ marginTop: 6 }}>
        <span className="item">
          <span className="swatch" style={{ background: 'var(--series-3)' }} />
          What it is worth at {Math.round(invested.chart_rate * 100)}% a year
        </span>
        <span className="item">
          <span className="swatch" style={{ background: 'var(--series-1)' }} />
          What you put in — {money(at30.contributed)} over thirty years
        </span>
      </div>

      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table>
          <thead>
            <tr>
              <th>If it returned</th>
              {invested.horizons.map((y) => (
                <th key={y} className="r">{y} years</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {invested.rates.map((r) => (
              <tr key={r.rate}>
                <td>
                  {r.label}{' '}
                  <span className="muted small">
                    {Math.round(r.rate * 100)}% a year
                  </span>
                </td>
                {invested.horizons.map((y) => (
                  <td key={y} className="r num">
                    {money(r.at[String(y)].value)}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <td className="muted">What you put in</td>
              {invested.horizons.map((y) => (
                <td key={y} className="r num muted">
                  {money(invested.rates[0].at[String(y)].contributed)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <p className="assumption" style={{ marginBottom: 0 }}>
        These are what the arithmetic gives if a constant average return
        happened every year, which is the one thing markets reliably do not
        do: the same long-run average arrives as good years and falling ones
        in an order nobody gets to choose, and a bad run early is worth far
        less than this suggests. Nothing here accounts for tax or for fees,
        and the figures are in today&apos;s dollars without inflation taken
        out — {money(at30.value)} in thirty years buys a good deal less than
        it does now. It is a sense of scale, not advice, and not a
        recommendation of anywhere in particular to put it.
      </p>
    </Card>
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
