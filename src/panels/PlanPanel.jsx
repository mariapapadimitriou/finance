import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, Notice, StatusPill, Why,
} from '../components/ui.jsx';
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

      <Card title="What comes in, and what is already spoken for"
            hint="Credit card statements can't see your pay or your rent — these are typed once">
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
        <Why id="plan.savings" label="Why is saving a commitment?">
          Savings counts as a commitment on purpose. Money you have decided to
          put away is not money you may spend, and treating it as leftover is
          how it stops happening.
        </Why>
      </Card>

      <Card title="Fixed commitments"
            hint="Rent, bills, insurance — the part no weekly number can influence">
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
                      <button className="btn quiet" disabled={busy}
                              onClick={() => run(() => deleteFixedCost(f.id))}>
                        Remove
                      </button>
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

      <Card title="What's left" hint="The only part a weekly number can move"
            actions={<StatusPill state={tone}>{
              { negative: 'Over-committed', tight: 'Tight', loose: 'Loose',
                ok: 'Workable', unset: 'Incomplete' }[data.verdict] ?? '—'
            }</StatusPill>}>
        <div className="sum">
          <Term label="Take-home" value={data.income} />
          <span className="op" aria-hidden="true">−</span>
          <Term label="Commitments" value={data.fixed_total}
                note={`${data.fixed.length} item${data.fixed.length === 1 ? '' : 's'}`} />
          <span className="op" aria-hidden="true">−</span>
          <Term label="Saving" value={data.savings} />
          {data.banks > 0 && (
            <>
              <span className="op" aria-hidden="true">−</span>
              <Term label="Piggy banks" value={data.banks}
                    note={`${data.bank_lines.length} bank${data.bank_lines.length === 1 ? '' : 's'}`} />
            </>
          )}
          <span className="op" aria-hidden="true">=</span>
          <Term label="Yours to spend" value={data.leftover} strong
                tone={data.leftover > 0 ? 'good' : 'bad'}
                note={data.income > 0 ? `${pct(data.leftover_share)} of your pay` : ''} />
        </div>
        <Notice kind={data.verdict === 'ok' ? 'good'
                      : data.verdict === 'negative' ? 'error' : undefined}>
          {data.note}
        </Notice>

        {data.leftover > 0 && data.daily_pool > 0 && (
          <>
          <p className="assumption" style={{ marginBottom: 0 }}>
            That {money(data.leftover)} has to cover groceries and the other
            essentials too, so it is not all pocket money. Of it,{' '}
            <strong className="num">{money(data.daily_pool)}</strong> is
            discretionary — which is what the weekly number on Today divides,
            about{' '}
            <strong className="num">{money(data.weekly_share)}</strong> a
            week through {monthLabel(data.month, { long: true })}. No amount
            of restraint on a Tuesday changes the grocery bill, so it is
            budgeted rather than handed out week by week.
          </p>
          <Why id="plan.split" label="Which categories count toward it?">
            That {money(data.daily_pool)} is the sum of the categories in the
            weekly number. Everything else —{' '}
            {essentialNames(data.categories).join(', ') || 'nothing, so far'} —
            has a budget of its own and stays out of the weekly figure. Budgets
            marks every line one way or the other.
            {data.bank_funded?.length > 0 && (
              <>
                <br /><br />
                {data.bank_funded.join(', ')}{' '}
                {data.bank_funded.length > 1 ? 'are' : 'is'} in neither. A
                piggy bank pays for {data.bank_funded.length > 1 ? 'them' : 'it'}{' '}
                — the <strong>Piggy banks</strong> term above, already
                subtracted — so that spending never touches your week.
              </>
            )}
          </Why>
          </>
        )}

        {/* These are about the plan, not the split: how much room the
            arithmetic leaves, and how much of the history it had to work
            from. They sat under the category table that used to follow. */}
        {data.headroom && <Notice>{data.headroom.note}</Notice>}
        {data.uncategorised && <Notice>{data.uncategorised}</Notice>}

        {data.leftover > 0 && (
          <div className="row" style={{ marginTop: 14, flexWrap: 'wrap', gap: 10 }}>
            <span className="small muted" style={{ flex: '1 1 240px' }}>
              {data.has_history
                ? 'How that divides across categories — and how this month is going against it — is on Budgets.'
                : 'Import a month or two and Budgets can divide that total in the proportions you already spend.'}
            </span>
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

function Term({ label, value, note, strong = false, tone }) {
  return (
    <div className={`term${strong ? ' strong' : ''}`}>
      <div className="k">{label}</div>
      <div className={`v num${tone ? ` ${tone}` : ''}`}>
        {money(value, { cents: true })}
      </div>
      {note && <div className="n">{note}</div>}
    </div>
  );
}

/** The categories budgeted monthly rather than handed out daily, biggest first. */
function essentialNames(categories) {
  return (categories ?? [])
    .filter((r) => r.essential)
    .sort((a, b) => b.budget - a.budget)
    .map((r) => r.category.toLowerCase());
}
