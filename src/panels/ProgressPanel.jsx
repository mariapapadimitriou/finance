import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice } from '../components/ui.jsx';
import { getProgress, money, monthLabel } from '../api.js';

/**
 * Progress: points, streaks and badges — every one of them earned by restraint.
 *
 * Nothing on this page pays out for spending. There is no currency to spend, no
 * streak that breaks because you didn't open the app, and no notification
 * pressure. It is all derived from the ledger on read, so correcting a
 * transaction immediately corrects the score.
 *
 * The day grid has three states and a fourth that matters more than the others:
 * a day outside the imported range reads *no data*, never "no spending". A
 * quiet-day badge for a month that was never imported would be a lie.
 */
export default function ProgressPanel({ month }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    getProgress(month).then((d) => live && setData(d)).catch((e) => live && setError(e));
    return () => { live = false; };
  }, [month]);

  if (!data && !error) return <Loading what="your streak" />;
  if (!data) return <ErrorNote error={error} />;

  const { level, streak, totals, badges, months } = data;
  const earned = badges.filter((b) => b.earned);

  return (
    <div className="stack">
      <Card className="hero-card">
        <div className="safe">
          <div>
            <div className="tile-label">Level</div>
            <div className="figure">{level.name}</div>
            <div className="caption">
              {level.points.toLocaleString()} points
              {level.next_at
                ? ` · ${(level.next_at - level.points).toLocaleString()} to ${level.next_name}`
                : ' · top level'}
            </div>
          </div>
          <div className="streak">
            <div className="big num">{streak.days}</div>
            <div className="tile-label">
              day{streak.days === 1 ? '' : 's'} under the allowance
            </div>
          </div>
        </div>

        <div className="bar-row" style={{ gridTemplateColumns: '1fr', margin: '16px 0 0' }}>
          <div className="track" style={{ height: 10 }}>
            <div className="fill" style={{ width: `${level.progress * 100}%` }} />
          </div>
        </div>
        <p className="assumption" style={{ marginBottom: 0 }}>
          Ten points for a day under the allowance, 25 for a day you spent
          nothing, 150 for a month finished inside budget, 40 more every seventh
          day of a streak. Every one of them is for restraint — nothing here pays
          out for spending, so it can never nudge you toward a purchase.
        </p>
      </Card>

      <div className="grid cols-4">
        <Stat label="Days under" value={totals.under_days} tone="good" />
        <Stat label="No-spend days" value={totals.no_spend_days} tone="good" />
        <Stat label="Days over" value={totals.over_days} />
        <Stat label="Months tracked" value={totals.months_tracked} />
      </div>

      <Card title="Badges" hint={`${earned.length} of ${badges.length} earned`}>
        <div className="badges">
          {badges.map((b) => (
            <div key={b.key} className={`badge${b.earned ? ' on' : ''}`}>
              <span className="mark" aria-hidden="true">{b.earned ? '★' : '☆'}</span>
              <div>
                <div className="bn">{b.name}</div>
                <div className="bd">{b.earned ? b.detail : b.description}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {months.length === 0 ? (
        <Notice>Import a statement and the day grid fills in.</Notice>
      ) : (
        <Card title="Day by day"
              hint="Green under the allowance · amber over · hollow means nothing spent">
          {months.map((m) => (
            <MonthRow key={m.month} m={m} highlight={m.month === month} />
          ))}
          <div className="legend" style={{ marginTop: 16 }}>
            <LegendKey cls="under" label="Under the allowance" />
            <LegendKey cls="no-spend" label="Nothing spent" />
            <LegendKey cls="over" label="Over" />
            <LegendKey cls="no-data" label="No statement for that day" />
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className={`value num${tone ? ` ${tone}` : ''}`}>{value}</div>
    </div>
  );
}

function MonthRow({ m, highlight }) {
  const overBudget = m.budget > 0 && m.spent > m.budget;
  // A month that was only partly imported can't be called "under budget" — the
  // missing days would have spending in them. Say what was imported instead.
  const note = m.fully_observed
    ? (m.ended ? (overBudget ? ' · went over' : ' · finished under') : ' · still running')
    : ` · only ${m.days_observed} of ${m.days_in_month} days imported`;

  return (
    <div className={`day-month${highlight ? ' current' : ''}`}>
      <div className="head">
        <strong>{monthLabel(m.month, { long: true })}</strong>
        <span className="muted small">
          {money(m.spent)} of {money(m.budget)}{note}
        </span>
      </div>
      <div className="days">
        {m.days.map((d) => (
          <span key={d.day} className={`day ${d.state}`}
                title={d.spent === null
                  ? `${d.day}: no statement covers this day`
                  : `${d.day}: ${d.spent === 0 ? 'nothing spent' : money(d.spent, { cents: true })}`}>
            <span className="sr-only">
              {d.day}: {d.state === 'no-data' ? 'no data' : d.state}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function LegendKey({ cls, label }) {
  return (
    <span className="item">
      <span className={`day ${cls}`} style={{ width: 11, height: 11 }} />
      {label}
    </span>
  );
}
