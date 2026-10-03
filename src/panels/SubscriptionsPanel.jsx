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
      <Empty title="No subscriptions found yet">
        They show up after three regular charges.
      </Empty>
    );
  }

  const active = items.filter((r) => r.active);
  // A lapse is a claim that you cancelled something, and three similar
  // charges that stopped describe a café you visited a few times just as
  // well. Only the regular ones are worth saying it about.
  const inactive = items.filter((r) => !r.active && r.confidence >= 0.6);

  return (
    <div className="stack">
      <div className="grid cols-4">
        <Tile label="Active" value={summary.count ?? 0} />
        <Tile label="Per month" value={money(summary.monthly_total ?? 0)} />
        <Tile label="Per year" value={money(summary.annual_total ?? 0)} />
        <Tile label="Stopped" value={inactive.length} />
      </div>

      <Card
        title="Active"
        hint="Subscriptions and regular bills"
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Merchant</th>
                <th>Category</th>
                <th>How often</th>
                <th className="r">Amount</th>
                <th className="r">Per year</th>
                <th>Next</th>
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
                    <span title="How regular the charges are">
                      <StatusPill state={r.confidence >= 0.8 ? 'good' : 'warning'}>
                        {pct(r.confidence)}
                      </StatusPill>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {inactive.length > 0 && (
        <Card
          title="Stopped"
          hint="Probably cancelled"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Merchant</th><th>How often</th>
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
