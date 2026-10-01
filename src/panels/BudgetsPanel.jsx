import { useEffect, useState } from 'react';
import { Card, Empty, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import { getBudgets, money, monthLabel, pct, setBudgets } from '../api.js';

/** Over budget, on pace to go over, or fine — status colour plus an icon and a word. */
function state(row) {
  if (row.spent > row.budget) return 'critical';
  if (!row.on_track) return 'warning';
  return 'good';
}

const STATE_TEXT = {
  critical: 'Over budget',
  warning: 'On pace to exceed',
  good: 'On track',
};

export default function BudgetsPanel({ month, summary, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  async function load() {
    setError(null);
    try {
      setData(await getBudgets(month));
    } catch (e) {
      setError(e);
    }
  }

  // `version` changes on an import, which changes what has been spent.
  useEffect(() => { load(); }, [month, version]);

  async function save() {
    setSaving(true);
    try {
      await setBudgets(draft);
      setDraft({});
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }


  if (error) return <ErrorNote error={error} onRetry={load} />;
  if (!data) return <Loading what="budgets" />;

  const rows = data.status ?? [];
  const partial = month === summary.latest_month && !summary.latest_month_complete;
  const running = partial && summary.latest_month_running;

  // No second budget suggester on this tab. Budgets come from the Plan
  // tab's arithmetic — income less commitments less savings, divided in your
  // own proportions. A rival one seeded from past spending could never ask
  // for less than last month, which is the whole point of the plan.
  return (
    <div className="stack">
      {rows.length === 0 ? (
        <Card title="No budgets set yet">
          <p className="muted">
            Budgets are worked out on the Plan tab: what you take home, less
            your commitments and what you&apos;re saving, divided across
            categories in the proportions you already spend them. That way the
            total is a decision and only the split comes from your history.
          </p>
          {onTab && (
            <button className="btn primary" style={{ marginTop: 14 }}
                    onClick={() => onTab('plan')}>
              Set up your plan
            </button>
          )}
        </Card>
      ) : (
        <>
          {partial && (
            <Notice>
              {running ? (
                <>
                  {monthLabel(month, { long: true })} is still in progress.
                  &ldquo;On pace&rdquo; projects your spending so far across the
                  whole month, so you can act before the month closes rather
                  than after.
                </>
              ) : (
                <>
                  {monthLabel(month, { long: true })} is over, but the data
                  stops short of its last day — so these totals may be missing
                  the end of the month. Sync on the Banks tab before treating
                  them as final.
                </>
              )}
            </Notice>
          )}

          {data.unbudgeted_spend > 1 && (
            <Notice>
              <strong>
                {money(data.unbudgeted_spend)} of this month&apos;s{' '}
                {money(data.month_spend)} isn&apos;t covered by any budget line.
              </strong>{' '}
              The bars below only count categories you have a budget for, so
              they will always read lower than the Overview until everything
              has one.{data.unbudgeted?.length > 0 && (
                <> Missing:{' '}
                  {data.unbudgeted.slice(0, 5).map((r) => r.category).join(', ')}
                  {data.unbudgeted.length > 5
                    && ` and ${data.unbudgeted.length - 5} more`}.</>
              )}
            </Notice>
          )}

          <Card title={`Budgets — ${monthLabel(month, { long: true })}`}
                hint="Spent against budget, with a projection for how the month is likely to end">
            <div className="stack" style={{ gap: 18 }}>
              {rows.map((r) => {
                const s = state(r);
                const used = Math.min(r.used, 1);
                return (
                  <div key={r.category}>
                    <div className="row" style={{ marginBottom: 8 }}>
                      <strong>{r.category}</strong>
                      <StatusPill state={s}>{STATE_TEXT[s]}</StatusPill>
                      <span className="spacer" />
                      <span className="num small">
                        {money(r.spent, { cents: true })} of {money(r.budget)}
                        {' '}
                        <span className="muted">({pct(r.used)})</span>
                      </span>
                    </div>
                    <div className="track" style={{
                      background: 'var(--surface-2)', borderRadius: 4,
                      height: 8, overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${used * 100}%`,
                        height: '100%',
                        borderRadius: '0 4px 4px 0',
                        background: `var(--${s === 'good' ? 'good' : s})`,
                      }} />
                    </div>
                    <div className="small muted" style={{ marginTop: 5 }}>
                      {r.on_track
                        ? `Projected ${money(r.projected)} by month end — ${money(r.remaining)} left.`
                        : `Projected ${money(r.projected)} by month end, ${money(Math.abs(r.projected_over))} over.`}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card title="Adjust budgets" hint="Set a category to 0 to remove its budget">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="r">Monthly budget</th>
                    <th className="r">Your median</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.category}>
                      <td>{r.category}</td>
                      <td className="r">
                        <input
                          type="number"
                          min="0"
                          step="10"
                          style={{ width: 110, textAlign: 'right' }}
                          value={draft[r.category] ?? r.budget}
                          onChange={(e) => setDraft((d) => ({
                            ...d, [r.category]: Number(e.target.value),
                          }))}
                          aria-label={`${r.category} monthly budget`}
                        />
                      </td>
                      <td className="r muted">{money(data.typical?.[r.category] ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn primary" onClick={save}
                      disabled={saving || Object.keys(draft).length === 0}>
                {saving ? 'Saving…' : 'Save changes'}
              </button>
              {Object.keys(draft).length > 0 && (
                <button className="btn quiet" onClick={() => setDraft({})}>Discard</button>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
