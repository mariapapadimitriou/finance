import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import { BarRow, Card, Legend, Notice, Tile } from '../components/ui.jsx';
import { dailySpendConfig, monthlyTrendConfig } from '../charts.js';
import { cssVar, getBreakdown, money, monthLabel, pct } from '../api.js';

export default function OverviewPanel({ summary, insights, theme, month, onMonth,
                                        version = 0 }) {
  const [showTable, setShowTable] = useState(false);

  const monthly = summary.monthly ?? [];
  const trendConfig = useMemo(() => monthlyTrendConfig(monthly), [monthly, theme]);
  const dailyConfig = useMemo(() => dailySpendConfig(summary.daily ?? []),
                              [summary.daily, theme]);

  // Server-rendered summary describes the latest month; anything month-specific
  // is refetched when the selector changes.
  const [breakdown, setBreakdown] = useState(null);

  useEffect(() => {
    if (!month) return undefined;
    let cancelled = false;
    getBreakdown(month)
      .then((d) => { if (!cancelled) setBreakdown(d); })
      .catch(() => { if (!cancelled) setBreakdown(null); });
    return () => { cancelled = true; };
    // `version` changes on an import, so the breakdown follows the new ledger
    // even when the selected month itself hasn't moved.
  }, [month, version]);

  const categories = (breakdown?.categories ?? []).filter((c) => c.amount > 0);
  const maxCategory = categories[0]?.amount ?? 0;
  const merchants = breakdown?.merchants ?? [];
  const maxMerchant = merchants[0]?.amount ?? 0;
  const split = breakdown?.split ?? {};
  // Two different situations that used to share one message. A month that
  // is still running will fill up on its own; a finished month the data
  // stops short of will not, and needs a sync rather than patience.
  const partial = month === summary.latest_month && !summary.latest_month_complete;
  const running = partial && summary.latest_month_running;
  const gaps = summary.coverage_gaps ?? [];

  const savings = insights?.summary?.weighted_annual ?? 0;
  const observedMonths = monthly.filter((m) => m.transactions > 0).length;
  const weekday = summary.weekday ?? [];
  const maxWeekday = Math.max(...weekday.map((d) => d.average), 0);

  return (
    <div className="stack">
      {gaps.length > 0 && (
        <Notice>
          <strong>{gaps.length} month{gaps.length === 1 ? '' : 's'} missing
          between {monthLabel(summary.months[0])} and{' '}
          {monthLabel(summary.months.at(-1))}.</strong>{' '}
          Averages and trends here only count the months you actually imported,
          so they stay honest — but a subscription whose charges straddle a gap
          can be missed entirely. Import the statements in between for the full
          picture.
        </Notice>
      )}

      {partial && (
        <Notice>
          {running ? (
            <>
              {monthLabel(month, { long: true })} is still in progress — your
              data runs to day {summary.date_range?.[1]?.slice(8)}. Comparisons
              against full months will read low until the month closes.
            </>
          ) : (
            <>
              <strong>
                {monthLabel(month, { long: true })} is over, but the data stops
                at day {summary.date_range?.[1]?.slice(8)}.
              </strong>{' '}
              That is either a quiet end to the month or a sync that hasn&apos;t
              run since — they look identical from here. Sync on the Banks tab
              to be sure before reading anything into this month.
            </>
          )}
        </Notice>
      )}

      <div className="grid cols-4">
        <Tile
          label={monthLabel(month, { long: true })}
          value={money(currentMonthSpend(summary, month))}
          delta={month === summary.latest_month ? summary.vs_average : undefined}
          note="vs a typical month"
        />
        {/* A median, not a mean — one holiday should not redefine normal.
            Labelled for what it is, and the same figure the Projections tab
            quotes, which it did not used to be. */}
        <Tile
          label="Typical month"
          value={money(summary.typical_monthly_spend ?? summary.average_monthly_spend)}
          note={`median of ${observedMonths} month${observedMonths === 1 ? '' : 's'} of data`}
        />
        <Tile
          label="Discretionary"
          value={pct(split.discretionary_share ?? 0)}
          note={`${money(split.discretionary ?? 0)} of ${money(split.total ?? 0)}`}
        />
        <Tile
          label="Could save"
          value={money(savings)}
          note="per year, confidence-weighted"
        />
      </div>

      <Card
        title="Month by month"
        hint="Card payments, transfers and refunds excluded; refunds net against their category"
        actions={
          <button className="btn quiet" onClick={() => setShowTable((v) => !v)}>
            {showTable ? 'Hide data' : 'Show data'}
          </button>
        }
      >
        <div className="chart">
          <Chart
            config={trendConfig}
            theme={theme}
            ariaLabel={`Monthly spending from ${monthLabel(monthly[0]?.month)} to ${monthLabel(monthly.at(-1)?.month)}`}
          />
        </div>
        {showTable && (
          <div className="table-wrap" style={{ marginTop: 14 }}>
            <table>
              <thead>
                <tr><th>Month</th><th className="r">Spend</th><th className="r">Transactions</th></tr>
              </thead>
              <tbody>
                {[...monthly].reverse().map((m) => (
                  <tr key={m.month}>
                    <td>{monthLabel(m.month, { long: true })}</td>
                    <td className="r">{money(m.spend, { cents: true })}</td>
                    <td className="r">{m.transactions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid cols-2">
        <Card title="Where it went" hint={monthLabel(month, { long: true })}>
          {categories.length === 0 ? (
            <p className="muted">
              {breakdown ? 'No spending recorded in this month.'
                         : 'Loading…'}
            </p>
          ) : (
            <div className="bars">
              {categories.slice(0, 10).map((c) => (
                <BarRow
                  key={c.category}
                  name={c.category}
                  sub={`${c.transactions} transaction${c.transactions === 1 ? '' : 's'} · ${pct(c.share)}`}
                  value={c.amount}
                  max={maxCategory}
                />
              ))}
            </div>
          )}
        </Card>

        <Card title="Top merchants" hint={monthLabel(month, { long: true })}>
          {merchants.length === 0 ? (
            <p className="muted">
              {breakdown ? 'No merchants in this month.' : 'Loading…'}
            </p>
          ) : (
            <div className="bars">
              {merchants.slice(0, 10).map((m) => (
                <BarRow
                  key={m.merchant}
                  name={m.merchant}
                  sub={`${m.category} · ${m.transactions}× · ${money(m.avg)} avg`}
                  value={m.amount}
                  max={maxMerchant}
                />
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid cols-2">
        <Card
          title="Fixed vs discretionary"
          hint="What you chose to spend, against what was already committed"
        >
          <div className="split-bar" role="img" aria-label={
            `Discretionary ${money(split.discretionary)}, fixed ${money(split.fixed)}`}>
            <span className="a" style={{ width: `${(split.discretionary_share ?? 0) * 100}%` }} />
            <span className="b" style={{ flex: 1 }} />
          </div>
          <Legend items={[
            { label: `Discretionary — ${money(split.discretionary ?? 0)}`, color: cssVar('--series-1') },
            { label: `Fixed — ${money(split.fixed ?? 0)}`, color: cssVar('--series-2') },
          ]} />
          <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
            Discretionary spending is the part you can actually move. Fixed
            commitments — rent, utilities, insurance — need renegotiating rather
            than restraint.
          </p>
        </Card>

        <Card title="Spend by weekday" hint="Average per active day, all history">
          {weekday.length === 0 ? (
            <p className="muted">Not enough data yet.</p>
          ) : (
            <div className="bars">
              {weekday.map((d) => (
                <BarRow key={d.day} name={d.day} value={d.average} max={maxWeekday} />
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Daily spending" hint="Last 90 days">
        <div className="chart short">
          <Chart config={dailyConfig} theme={theme} ariaLabel="Daily spending over the last 90 days" />
        </div>
      </Card>

      <Card title="Your cards" hint="Spending aggregated across every card you've imported">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Card</th>
                <th className="r">Transactions</th>
                <th className="r">Total spend</th>
              </tr>
            </thead>
            <tbody>
              {(summary.accounts ?? []).map((a) => (
                <tr key={a.account_id}>
                  <td className="merchant">{a.account_name}</td>
                  <td className="r">{a.transactions}</td>
                  <td className="r">{money(a.amount, { cents: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function currentMonthSpend(summary, month) {
  return summary.monthly?.find((m) => m.month === month)?.spend ?? 0;
}
