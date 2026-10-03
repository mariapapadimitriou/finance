import { useCallback, useEffect, useState } from 'react';
import Chart from '../components/Chart.jsx';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
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
      // The same endpoint and the same setting the Plan tab writes. One
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

      {/* Shown, not edited. Take-home pay had a Save button here and another on
          the Plan tab, both writing the same setting, and whichever was touched
          last won silently. One figure, one place to change it. */}
      <Card>
        <p className="small" style={{ margin: 0 }}>
          Take-home pay of{' '}
          <strong className="num">{money(data.monthly_income)}</strong> a month
          {data.basis?.from_plan && (
            <>, less {money(data.basis.fixed_total)} in bills</>
          )}
          .{' '}
          {onTab
            ? <button className="link" onClick={() => onTab('plan')}>
                Edit
              </button>
            : null}
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
          {!data.from_plan && (
            <Notice>
              Add your bills on the Plan for a real figure — for now this is a
              best case, counting only your imported cards.
            </Notice>
          )}

          {data.from_plan ? (
            <>
              <div className="grid cols-3">
                <Tile label="You put away" value={money(data.basis.saving)}
                      note="from your plan" tone="good" />
                <Tile label="Left unspent" value={money(data.basis.unspent)}
                      note={`${money(data.basis.typical_spend)} of ${money(data.basis.leftover)} usually spent`}
                      tone={data.basis.unspent < 0 ? 'bad' : 'good'} />
                <Tile label="Saved each month" value={money(data.monthly_surplus)}
                      note="both together"
                      tone={data.monthly_surplus < 0 ? 'bad' : 'good'} />
              </div>
              <div className="grid cols-2">
                <Tile label="Cuts found" value={money(data.monthly_cuts)}
                      note="a month, from Savings" tone="good" />
                <Tile label="Typical spend" value={money(data.typical_monthly_spend)}
                      note={`median of ${data.months_observed} month`
                            + `${data.months_observed === 1 ? '' : 's'}`} />
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

          {data.from_plan && (
            <SavingsSlider
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

          <Card
            title="Twelve months out"
            hint="Saved by following the plan vs. your recent pace"
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
              {data.at_12.on_plan >= data.at_12.pace
                ? <>Sticking to the plan saves{' '}
                    <strong className="num">{money(data.at_12.on_plan - data.at_12.pace)}</strong>{' '}
                    more this year.</>
                : <>You&apos;re beating the plan by{' '}
                    <strong className="num">{money(data.at_12.pace - data.at_12.on_plan)}</strong>{' '}
                    a year — consider raising your savings.</>}
            </p>
          </Card>

          <Card title="How long to save…">
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
                        : 'not at this pace'}
                      tone={data.goal.pace_months ? undefined : 'bad'} />
                <Tile label="Following the plan"
                      value={data.goal.plan_months
                        ? `${data.goal.plan_months} months`
                        : 'Never'}
                      note={data.monthly_on_plan !== null
                            && data.monthly_on_plan !== undefined
                        ? `${money(data.monthly_on_plan)} a month`
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
                         dirty }) {
  const ceiling = Math.max(data.savings_ceiling ?? 0, value, 100);
  const max = Math.ceil(ceiling / 25) * 25;
  const filled = Math.round((value / max) * 100);
  const months = data.year_end?.months ?? 0;
  const from = MONTH_NAMES[12 - months] ?? '';

  return (
    <Card title="What if you saved more?"
          actions={dirty && (
            <div className="row" style={{ gap: 8 }}>
              <button className="btn quiet" onClick={onReset} disabled={saving}>
                Reset
              </button>
              <button className="btn primary" onClick={onCommit} disabled={saving}>
                {saving ? 'Saving…' : 'Save to plan'}
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

      <div className="grid cols-3" style={{ marginTop: 16 }}>
        <Tile label={`By 31 December`} value={money(data.year_end?.on_plan ?? 0)}
              note={months > 0
                ? `${months} more month${months === 1 ? '' : 's'}, ${from} on`
                : 'the year is done'}
              tone="good" />
        <Tile label="Over twelve months" value={money(data.at_12?.on_plan ?? 0)}
              note="following the plan" tone="good" />
        <Tile label="Left to spend" value={money(data.basis?.leftover ?? 0)}
              note="a month"
              tone={(data.basis?.leftover ?? 0) <= 0 ? 'bad' : undefined} />
      </div>

      <p className="assumption" style={{ marginBottom: 0 }}>
        Saving more lowers what you can spend each day.
      </p>
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
    <Card title="If you invested it"
          hint={`${money(invested.monthly)} a month, compounded`}>
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
        Illustrative only — ignores tax, fees, inflation and market swings.
        Not advice.
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
      {months} month{months === 1 ? '' : 's'} of data
    </StatusPill>
  );
}
