import { Card, Empty, StatusPill, Tile } from '../components/ui.jsx';
import { dateLabel, money, pct } from '../api.js';

const CADENCE_LABEL = {
  weekly: 'Weekly', biweekly: 'Every 2 weeks', monthly: 'Monthly',
  quarterly: 'Quarterly', semiannual: 'Twice a year', annual: 'Yearly',
};

export default function SubscriptionsPanel({ recurring }) {
  const items = recurring?.recurring ?? [];
  const summary = recurring?.summary ?? {};

  if (items.length === 0) {
    return (
      <Empty title="No recurring charges detected yet">
        A charge needs to appear at least three times on a regular cadence before
        it counts as recurring. Import a longer history and subscriptions will
        surface here automatically.
      </Empty>
    );
  }

  const active = items.filter((r) => r.active);
  const inactive = items.filter((r) => !r.active);

  return (
    <div className="stack">
      <div className="grid cols-4">
        <Tile label="Active subscriptions" value={summary.count ?? 0}
              note="detected from charge regularity, not merchant names" />
        <Tile label="Every month" value={money(summary.monthly_total ?? 0)}
              note="renewing without a decision" />
        <Tile label="Every year" value={money(summary.annual_total ?? 0)}
              note="total committed annually" />
        <Tile label="Lapsed" value={inactive.length}
              note="past due for their next charge" />
      </div>

      <Card
        title="Active recurring charges"
        hint="Detected by cadence and amount stability — includes bills as well as subscriptions"
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Category</th>
                <th>Cadence</th>
                <th className="r">Amount</th>
                <th className="r">Per year</th>
                <th>Next expected</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {active.map((r) => (
                <tr key={`${r.merchant}-${r.amount}`}>
                  <td className="merchant">
                    {r.merchant}
                    {r.price_change?.direction === 'increase' && (
                      <div className="desc" style={{ color: 'var(--critical)' }}>
                        ↑ {money(r.price_change.from, { cents: true })} →{' '}
                        {money(r.price_change.to, { cents: true })}
                        {' '}({pct(r.price_change.pct)})
                      </div>
                    )}
                    {r.price_change?.direction === 'decrease' && (
                      <div className="desc">
                        ↓ {money(r.price_change.from, { cents: true })} →{' '}
                        {money(r.price_change.to, { cents: true })}
                      </div>
                    )}
                  </td>
                  <td className="muted">{r.category}</td>
                  <td>{CADENCE_LABEL[r.cadence] ?? r.cadence}</td>
                  <td className="r">{money(r.amount, { cents: true })}</td>
                  <td className="r">{money(r.annual_cost)}</td>
                  <td className="muted">{dateLabel(r.next_expected)}</td>
                  <td>
                    <StatusPill state={r.confidence >= 0.8 ? 'good' : 'warning'}>
                      {pct(r.confidence)}
                    </StatusPill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
          Confidence reflects how regular the charges are — how many there have
          been, how evenly spaced, and how stable the amount. A lower score
          usually means an irregular bill rather than a subscription.
        </p>
      </Card>

      {inactive.length > 0 && (
        <Card
          title="Lapsed or cancelled"
          hint="Past their expected next charge — likely already cancelled"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Merchant</th><th>Cadence</th>
                  <th className="r">Amount</th><th>Last charged</th>
                  <th className="r">Paid in total</th>
                </tr>
              </thead>
              <tbody>
                {inactive.map((r) => (
                  <tr key={`${r.merchant}-${r.amount}`}>
                    <td className="merchant">{r.merchant}</td>
                    <td>{CADENCE_LABEL[r.cadence] ?? r.cadence}</td>
                    <td className="r">{money(r.amount, { cents: true })}</td>
                    <td className="muted">
                      {dateLabel(r.last_seen)} · {r.days_since_last} days ago
                    </td>
                    <td className="r">{money(r.total_paid)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
