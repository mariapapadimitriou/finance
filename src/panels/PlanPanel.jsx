import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, Notice, StatusPill, } from '../components/ui.jsx';
import { Donut, RingLegend, RingRow } from '../components/Ring.jsx';
import {
  addFixedCost, deleteFixedCost, getCategories, getPlanSetup,
  money, monthLabel, pct, savePlanSetup,
} from '../api.js';

/**
 * The plan: income in, commitments and savings out, the rest divided up.
 *
 * This is the one screen in the app that is not derived from the ledger, and
 * it has to exist. A budget taken from your own past spending cannot ask you
 * to spend less — it is a description of a habit wearing a plan's clothes,
 * and a bad year quietly becomes the target.
 *
 * So the total is arithmetic on figures you enter, and history is used only
 * for the split: the shares are yours, the total is the arithmetic's.
 *
 * The split itself is not here. It used to be, as a table of every category —
 * which meant the same list appeared on this page and twice more on Budgets,
 * and the figure you were reading depended on which card you had reached. This
 * page answers what the money is promised to; Budgets answers how the rest
 * divides and how the month is going against it.
 */
export default function PlanPanel({ onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [cats, setCats] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [income, setIncome] = useState('');
  const [savings, setSavings] = useState('');
  const [draft, setDraft] = useState({ name: '', amount: '', category: 'Rent & Housing' });

  const load = useCallback(async () => {
    setError(null);
    try {
      const d = await getPlanSetup();
      setData(d);
      setIncome(d.income ? String(d.income) : '');
      setSavings(d.savings ? String(d.savings) : '');
      // The endpoint returns objects, not strings; the select wants names.
      const list = (await getCategories().catch(() => null))?.categories ?? [];
      setCats(list.map((c) => (typeof c === 'string' ? c : c.name)));
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function run(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading what="your plan" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const tone = { negative: 'critical', tight: 'warning', loose: 'warning',
                 ok: 'good', unset: 'warning' }[data.verdict] ?? 'warning';

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      <Card title="Income">
        <form className="controls" onSubmit={(e) => {
          e.preventDefault();
          run(() => savePlanSetup(Number(income) || 0, Number(savings) || 0));
        }}>
          <label htmlFor="income">Monthly take-home</label>
          <input id="income" type="number" min="0" step="any" inputMode="decimal"
                 value={income} onChange={(e) => setIncome(e.target.value)}
                 style={{ width: 130 }} />
          <label htmlFor="savings">Saving / investing</label>
          <input id="savings" type="number" min="0" step="any" inputMode="decimal"
                 value={savings} onChange={(e) => setSavings(e.target.value)}
                 style={{ width: 130 }} />
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </form>
      </Card>

      <Card title="Fixed commitments">
        {data.fixed.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Commitment</th><th>Category</th>
                  <th className="r">Monthly</th><th /></tr>
              </thead>
              <tbody>
                {data.fixed.map((f) => (
                  <tr key={f.id}>
                    <td className="merchant">{f.name}</td>
                    <td className="muted">{f.category}</td>
                    <td className="r num">{money(f.amount, { cents: true })}</td>
                    <td className="r">
                      {/* The mortgage's line is its payment, worked out on
                          its own page; changing it here would disagree. */}
                      {f.from === 'mortgage' ? (
                        onTab ? (
                          <button className="btn quiet" onClick={() => onTab('mortgage')}>
                            Mortgage
                          </button>
                        ) : <span className="muted small">from Mortgage</span>
                      ) : (
                        <button className="btn quiet" disabled={busy}
                                onClick={() => run(() => deleteFixedCost(f.id))}>
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <form className="controls" style={{ marginTop: data.fixed.length ? 14 : 0 }}
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  await addFixedCost({ name: draft.name,
                                       amount: Number(draft.amount) || 0,
                                       category: draft.category });
                  setDraft({ name: '', amount: '', category: draft.category });
                });
              }}>
          <input type="text" value={draft.name} required placeholder="Rent"
                 aria-label="Commitment name" style={{ flex: '1 1 160px' }}
                 onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <select value={draft.category} aria-label="Category"
                  onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
            {cats.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input type="number" min="0" step="any" required inputMode="decimal"
                 value={draft.amount} placeholder="0" aria-label="Monthly amount"
                 style={{ width: 110 }}
                 onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
          <button className="btn" type="submit" disabled={busy}>Add</button>
        </form>
      </Card>

      <Card title="What's left"
            actions={<StatusPill state={tone}>{
              { negative: 'Over-committed', tight: 'Tight', loose: 'Loose',
                ok: 'Workable', unset: 'Incomplete' }[data.verdict] ?? '—'
            }</StatusPill>}>
        <IncomeRing data={data} />
        {data.leftover > 0 && (
          <div className="row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
            {onTab && (
              <button className="btn" onClick={() => onTab('budgets')}>
                Budgets
              </button>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

/**
 * Take-home pay as a donut: what is promised away, and the part that is yours.
 *
 * When the plan promises more than comes in, the ring is drawn against what
 * is promised instead, and the middle says by how much it is short.
 */
function IncomeRing({ data }) {
  const parts = [
    { label: 'Commitments', value: data.fixed_total, color: 'var(--ring-2)' },
    { label: 'Saving', value: data.savings, color: 'var(--ring-1)' },
    data.banks > 0 && { label: 'Piggy banks', value: data.banks, color: 'var(--ring-4)' },
    { label: 'Yours to spend', value: Math.max(data.leftover, 0), color: 'var(--ring-3)' },
  ].filter(Boolean);
  const short = data.leftover < 0;

  return (
    <RingRow>
      <Donut size={168} thickness={16}
             segments={parts.map((p) => ({ ...p, title: money(p.value) }))}
             total={short ? undefined : data.income}>
        <div className={`big num${short ? ' bad' : ''}`}>{money(Math.abs(data.leftover))}</div>
        <div className="under">
          {short ? 'Short' : data.income > 0 ? `${pct(data.leftover_share)} yours` : 'Yours'}
        </div>
      </Donut>
      <RingLegend items={[
        { label: 'Take-home', value: money(data.income, { cents: true }), icon: 'flag' },
        ...parts.map((p) => ({
          label: p.label, color: p.color,
          value: money(p.label === 'Yours to spend' ? data.leftover : p.value, { cents: true }),
          tone: p.label === 'Yours to spend' && short ? 'bad' : undefined,
        })),
      ]} />
    </RingRow>
  );
}

/** The categories budgeted monthly rather than handed out daily, biggest first. */
function essentialNames(categories) {
  return (categories ?? [])
    .filter((r) => r.essential)
    .sort((a, b) => b.budget - a.budget)
    .map((r) => r.category.toLowerCase());
}
