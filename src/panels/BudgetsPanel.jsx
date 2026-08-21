import { useEffect, useState } from 'react';
import { Card, Empty, ErrorNote, Loading, StatusPill } from '../components/ui.jsx';
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

export default function BudgetsPanel({ month, summary }) {
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

  useEffect(() => { load(); }, [month]);

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

  async function seed() {
    setSaving(true);
    try {
      await setBudgets(data.suggested);
      await load();
    } finally {
      setSaving(false);
    }
  }

  if (error) return <ErrorNote error={error} onRetry={load} />;
  if (!data) return <Loading what="budgets" />;

  const rows = data.status ?? [];
  const suggested = Object.entries(data.suggested ?? {});
  const partial = month === summary.latest_month && !summary.latest_month_complete;

  return (
    <div className="stack">
      {rows.length === 0 ? (
        <Card title="No budgets set yet">
          <p className="muted">
            Budgets here are seeded from what you actually spend rather than a
            generic template. Discretionary categories are proposed 10% below
            your own median — a nudge, not a cliff — while essentials are set at
            your median, since deciding to use less electricity doesn&apos;t make
            it so.
          </p>
          {suggested.length > 0 ? (
            <>
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr><th>Category</th><th className="r">Suggested monthly budget</th></tr>
                  </thead>
                  <tbody>
                    {suggested.map(([cat, amt]) => (
                      <tr key={cat}>
                        <td>{cat}</td>
                        <td className="r">{money(amt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button className="btn primary" onClick={seed} disabled={saving}
                      style={{ marginTop: 14 }}>
                {saving ? 'Setting…' : `Use these ${suggested.length} budgets`}
              </button>
            </>
          ) : (
            <Empty title="Not enough history to suggest budgets">
              Import a few months of statements first.
            </Empty>
          )}
        </Card>
      ) : (
        <>
          {partial && (
            <div className="notice">
              {monthLabel(month, { long: true })} is still in progress. &ldquo;On
              pace&rdquo; projects your spending so far across the whole month, so
              you can act before the month closes rather than after.
            </div>
          )}

          <Card title={`Budgets — ${monthLabel(month, { long: true })}`}
                hint="Spent against budget, with a projection for how the month is likely to end">
            <div className="stack" style={{ gap: 18 }}>
              {rows.map((r) => {
                const s = state(r);
                const used = Math.min(r.used, 1);
                return (
                  <div key={r.category}>
                    <div className="row" style={{ marginBottom: 6 }}>
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
                      height: 14, overflow: 'hidden',
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
                      <td className="r muted">{money(data.suggested?.[r.category] ?? 0)}</td>
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
