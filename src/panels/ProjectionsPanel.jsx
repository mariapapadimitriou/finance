import { useCallback, useEffect, useState } from 'react';
import Chart from '../components/Chart.jsx';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import { getProjections, money, setIncome } from '../api.js';
import { projectionConfig } from '../charts.js';

/**
 * Projections: two lines, and the gap between them is the whole point.
 *
 * *Current pace* carries your own surplus forward. *With cuts* adds the savings
 * the engine has already found and priced. Neither is a forecast — they are
 * arithmetic on a trend, and the honest part is saying how thin that trend is,
 * so the months behind the numbers travel with them.
 */
export default function ProjectionsPanel({ insights, version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState('');
  const [income, setIncomeDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (goal) => {
    setError(null);
    try {
      const d = await getProjections(goal || undefined);
      setData(d);
      setIncomeDraft((v) => v || (d.configured_income ? String(d.configured_income) : ''));
    } catch (e) {
      setError(e);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);   // an import changes the spend history the projection rests on

  useEffect(() => { load(target); }, [load, target]);

  async function saveIncome(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await setIncome(Number(income || 0));
      await load(target);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading what="projections" />;

  const foundAnnual = insights?.summary?.weighted_annual ?? 0;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={() => load(target)} />

      <Card title="Monthly take-home pay"
            hint="Credit card statements don't show income, so this one has to be typed">
        <form className="controls" onSubmit={saveIncome}>
          <label htmlFor="income">After tax, each month I take home</label>
          <input id="income" type="number" min="0" step="50" value={income}
                 onChange={(e) => setIncomeDraft(e.target.value)}
                 placeholder="e.g. 4200" style={{ width: 140 }} />
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </form>
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
          {/* Stated before the numbers rather than under them. The surplus is
              take-home minus what touched these cards — rent paid by transfer,
              another card and cash are all missing from it, so read as a
              savings rate it is far too high. */}
          <Notice>
            <strong>Read the surplus as a ceiling.</strong> {data.caveat}
          </Notice>

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

          <Card
            title="Twelve months out"
            hint="Cumulative savings, current pace against pace with the cuts applied"
            actions={<Confidence level={data.confidence}
                                 months={data.months_observed} />}
          >
            <div className="chart">
              <Chart
                config={projectionConfig(data.series)}
                ariaLabel={`Cumulative savings over twelve months: `
                  + `${money(data.at_12.current)} at the current pace, `
                  + `${money(data.at_12.with_cuts)} with the cuts applied`}
              />
            </div>
            <div className="legend" style={{ marginTop: 6 }}>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-1)' }} />
                Current pace — {money(data.at_12.current)} by month 12
              </span>
              <span className="item">
                <span className="swatch" style={{ background: 'var(--series-3)' }} />
                With cuts — {money(data.at_12.with_cuts)} by month 12
              </span>
            </div>
            <p className="assumption" style={{ marginBottom: 0 }}>
              The gap between the lines is{' '}
              {money(data.at_12.with_cuts - data.at_12.current)} over the year,
              which is what acting on the findings is worth
              {foundAnnual > 0 && ' — already weighted for how likely each one is to stick'}.
              Both lines move with the same surplus underneath them, so the gap
              holds even where the surplus itself is too generous.
            </p>
          </Card>

          <Card title="How long until…"
                hint="A number you have in mind, under each pace">
            <form className="controls" onSubmit={(e) => e.preventDefault()}>
              <label htmlFor="target">I want to save</label>
              <input id="target" type="number" min="0" step="500" value={target}
                     onChange={(e) => setTarget(e.target.value)}
                     placeholder="5,000" style={{ width: 140 }} />
            </form>

            {data.goal && (
              <div className="grid cols-2" style={{ marginTop: 16 }}>
                <Tile label="At your current pace"
                      value={data.goal.current_months
                        ? `${data.goal.current_months} months`
                        : 'Never'}
                      note={data.goal.current_months
                        ? `${money(data.monthly_surplus)} a month`
                        : 'this pace saves nothing'}
                      tone={data.goal.current_months ? undefined : 'bad'} />
                <Tile label="With the cuts applied"
                      value={data.goal.with_cuts_months
                        ? `${data.goal.with_cuts_months} months`
                        : 'Never'}
                      note={data.goal.current_months && data.goal.with_cuts_months
                        ? `${data.goal.current_months - data.goal.with_cuts_months} months sooner`
                        : `${money(data.monthly_surplus + data.monthly_cuts)} a month`}
                      tone="good" />
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
