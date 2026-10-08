import { useCallback, useEffect, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, StatusPill, } from '../components/ui.jsx';
import { getProjections, money, monthLabel, saveSavings } from '../api.js';
import { investedConfig, projectionConfig } from '../charts.js';
import { OPEN_SAVED_KEY } from './TransactionsPanel.jsx';

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November',
                     'December'];

/**
 * Ahead: the plan against your current pace, and what saving gets you.
 *
 * *Plan* is what the plan puts away. *Current pace* is that plus whatever this
 * month's spending, carried to its end, leaves of the budget — so the gap
 * between them is how this month is going, a month at a time.
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
          <div className="row">
            <strong className="num">{money(data.monthly_income)}</strong>
            <span className="muted">a month</span>
            <span className="spacer" />
            <GoTo to="plan" from="projections" onTab={onTab}>Edit</GoTo>
          </div>
        </Card>
      )}

      {!data?.available ? (
        <Notice>
          {data?.reason}

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


          <Card
            title="Plan vs current pace"
            actions={<Confidence level={data.confidence}
                                 months={data.months_observed} />}
          >
            <PaceBadge data={data} />
            <div className="chart">
              <Chart
                config={projectionConfig(data.series)}
                ariaLabel={`Saved over twelve months: `
                  + `${money(data.at_12.on_plan)} on the plan, `
                  + `${money(data.at_12.pace)} at your current pace`}
              />
            </div>
            <div className="legend" style={{ marginTop: 6 }}>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-3)' }} />
                Plan — {money(data.at_12.on_plan)} in 12 months
              </span>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-1)' }} />
                Current pace — {money(data.at_12.pace)}
              </span>
            </div>
          </Card>

          {data.invested_month && <InvestedThisMonth im={data.invested_month} onTab={onTab} />}

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

      {/* Live state, so never folded away with the explanation below. */}
      {dirty && (
        <p className="small muted" style={{ margin: '14px 0 0' }}>Not saved</p>
      )}

      {/* The thing a slider like this usually hides: it is not a tap that
          makes more money come out. The recent-pace line does not move at
          all, because what you actually accumulate is unchanged — what
          changes is how much of it was a decision. */}
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
    <Card title="If invested">
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
      {months} month{months === 1 ? '' : 's'}
    </StatusPill>
  );
}

/**
 * How this month is going against the plan, as one badge: ahead (spending
 * under the budget) or behind, a month at a time.
 */
function PaceBadge({ data }) {
  const pm = data.pace_month;
  if (data.ahead == null || !pm) return null;
  const ahead = data.ahead >= 0;
  return (
    <div className="pace-badge-row">
      <span className={`pace-badge ${ahead ? 'good' : 'bad'}`}>
        {ahead ? '▲' : '▼'} {money(Math.abs(data.ahead))} a month {ahead ? 'ahead of' : 'behind'} plan
      </span>
      <span className="small muted">
        On pace to spend {money(pm.projected_spend)} of {money(pm.leftover)}
        {pm.basis === '30 days' ? ' (last 30 days)' : ` in ${monthLabel(pm.month, { long: true })}`}
      </span>
    </div>
  );
}

/**
 * What was actually put away this month, beside the saving the plan asks
 * for: transfers marked Saved, plus the saved part of any other transaction.
 */
function InvestedThisMonth({ im, onTab }) {
  function seeSaved() {
    // Read once by the Transactions page, which opens on what's saved.
    try { window.sessionStorage.setItem(OPEN_SAVED_KEY, '1'); } catch { /* fine */ }
    onTab?.('transactions');
  }
  const target = im.saving ?? 0;
  const done = target > 0 && im.amount >= target - 0.5;
  const share = target > 0 ? Math.min(Math.max(im.amount, 0) / target, 1) : 0;
  return (
    <Card title="Saved this month"
          actions={onTab && (
            <button className="link-btn" onClick={seeSaved}>See what's counted</button>
          )}>
      {im.amount > 0 ? (
        <>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <strong className="num" style={{ fontSize: '1.5rem' }}>{money(im.amount)}</strong>
            {target > 0 && (
              <span className="muted">of your {money(target)} saving</span>
            )}
            <span className="spacer" />
            {done && <StatusPill state="good">Done</StatusPill>}
          </div>
          {target > 0 && (
            <div className="track" style={{ background: 'var(--surface-2)', borderRadius: 4,
                                             height: 8, overflow: 'hidden', marginTop: 10 }}>
              <div style={{ width: `${share * 100}%`, height: '100%', borderRadius: 4,
                            background: done ? 'var(--good)' : 'var(--brand)' }} />
            </div>
          )}
        </>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          Nothing marked as saved yet. Sort a transfer as Saved on
          Transactions, or mark part of one under Split….
        </p>
      )}
    </Card>
  );
}
