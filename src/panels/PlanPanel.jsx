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
// With nothing set, the goal is a fifth of take-home.
const DEFAULT_RATE = 20;
const CHIPS = [10, 15, 20];

export default function PlanPanel({ onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [cats, setCats] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [income, setIncome] = useState('');
  // The saving goal, as a percentage of take-home.
  const [rate, setRate] = useState(String(DEFAULT_RATE));
  const [draft, setDraft] = useState({ name: '', amount: '', category: 'Rent & Housing' });

  const load = useCallback(async () => {
    setError(null);
    try {
      const d = await getPlanSetup();
      setData(d);
      setIncome(d.income ? String(d.income) : '');
      setRate(d.savings_rate != null
        ? String(Math.round(d.savings_rate * 1000) / 10) : String(DEFAULT_RATE));
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

  const seen = data.observed;
  const span = seen?.months?.length
    ? `${monthLabel(seen.months[0].month)}–${monthLabel(seen.months.at(-1).month)}` : '';
  const goal = Math.round((Number(income) || 0) * (Number(rate) || 0) / 100);

  const tone = { negative: 'critical', tight: 'warning', loose: 'warning',
                 ok: 'good', unset: 'warning' }[data.verdict] ?? 'warning';

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      <Card title="Income">
        <form className="stack" style={{ gap: 14 }} onSubmit={(e) => {
          e.preventDefault();
          run(() => savePlanSetup(Number(income) || 0, (Number(rate) || 0) / 100));
        }}>
          <div className="plan-field">
            <label htmlFor="income">Monthly take-home</label>
            <input id="income" type="number" min="0" step="any" inputMode="decimal"
                   value={income} onChange={(e) => setIncome(e.target.value)}
                   style={{ width: 140 }} />
            {seen && Math.abs(seen.income - (Number(income) || 0)) > 1 && (
              <div className="muted small">
                From your accounts: about <strong className="num">{money(seen.income)}</strong>/mo
                {' '}({span}) ·{' '}
                <button type="button" className="link-btn"
                        onClick={() => setIncome(String(Math.round(seen.income)))}>
                  Use this
                </button>
              </div>
            )}
          </div>
          <div className="plan-field">
            <label htmlFor="rate">Saving goal</label>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <span className="row" style={{ gap: 4 }}>
                <input id="rate" type="number" min="0" max="90" step="any" inputMode="decimal"
                       value={rate} onChange={(e) => setRate(e.target.value)}
                       style={{ width: 80 }} aria-label="Saving goal, percent of take-home" />
                <span className="muted">%</span>
              </span>
              {CHIPS.map((c) => (
                <button key={c} type="button"
                        className={`pill-btn${Number(rate) === c ? ' on' : ''}`}
                        onClick={() => setRate(String(c))}>{c}%</button>
              ))}
              <span className="num">= <strong>{money(goal)}</strong>/mo</span>
            </div>
          </div>
          <div>
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Card>

      {seen && <GoalVsActual seen={seen} goal={data.savings} income={data.income} />}

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
                Split it into budgets
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
    { label: 'Saving goal', value: data.savings, color: 'var(--ring-1)' },
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

/**
 * The goal beside what actually happened, averaged over recent full months:
 * what stayed with you (income minus everything spent) and what you moved to
 * savings. Bars are measured against the goal.
 */
function GoalVsActual({ seen, goal, income }) {
  const base = income > 0 ? income : seen.income;
  const rows = [
    { label: 'Saving goal', value: goal },
    { label: 'Stayed with you', note: 'income − spending', value: seen.stayed },
    { label: 'Moved to savings', note: 'marked Saved', value: seen.moved },
  ];
  const top = Math.max(goal, seen.stayed, seen.moved, 1);
  const short = goal > 0 && seen.stayed < goal;
  return (
    <Card title="Saving: goal vs actual">
      <ul className="goal-rows">
        {rows.map((r, i) => (
          <li key={r.label}>
            <div className="goal-label">
              <span>{r.label}</span>
              {r.note && <span className="muted small"> · {r.note}</span>}
            </div>
            <div className="goal-bar" aria-hidden="true">
              <div className={i === 0 ? 'goal' : r.value >= goal ? 'good' : 'short'}
                   style={{ width: `${Math.max(Math.min(r.value / top, 1), 0) * 100}%` }} />
            </div>
            <div className="goal-value num">
              <strong>{money(r.value)}</strong>
              {base > 0 && <span className="muted small"> {pct(r.value / base)}</span>}
            </div>
          </li>
        ))}
      </ul>
      <p className="muted small" style={{ margin: '10px 0 0' }}>
        {seen.months.map((m) => `${monthLabel(m.month)} ${money(m.stayed)}`).join(' · ')} stayed
        {short && (
          <span className="warn-text"> · short of goal by {money(goal - seen.stayed)}/mo</span>
        )}
      </p>
    </Card>
  );
}

/** The categories budgeted monthly rather than handed out daily, biggest first. */
function essentialNames(categories) {
  return (categories ?? [])
    .filter((r) => r.essential)
    .sort((a, b) => b.budget - a.budget)
    .map((r) => r.category.toLowerCase());
}
