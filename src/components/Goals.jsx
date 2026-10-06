import { useEffect, useState } from 'react';
import { Card, ErrorNote } from './ui.jsx';
import { Donut } from './Ring.jsx';
import {
  addGoal, deleteGoal, depositToGoal, editGoal, getGoals, money, monthLabel,
} from '../api.js';

const CELEBRATED = 'spendie.goals.celebrated';

function celebrated() {
  try { return new Set(JSON.parse(localStorage.getItem(CELEBRATED) || '[]')); } catch { return new Set(); }
}
function markCelebrated(id) {
  try {
    const seen = celebrated();
    seen.add(id);
    localStorage.setItem(CELEBRATED, JSON.stringify([...seen]));
  } catch { /* a celebration per visit, then */ }
}

// Names that sound like money that will be spent on a card — a trip, a gift.
// That belongs in a piggy bank, which pays for the charges when they come, so
// they don't land on the weekly allowance.
const SPENDING = /\b(trip|travel|vacation|holiday|flights?|hotel|getaway|gifts?|christmas|birthday|wedding|honeymoon|concerts?|festival|tickets?|car repairs?)\b/i;

export function soundsLikeSpending(name) {
  return SPENDING.test(name || '');
}

/**
 * Savings goals: money you are keeping — an emergency fund, a down payment —
 * with a ring for how far along each one is and the month it lands. When
 * spending is running under the plan, each goal also says how much sooner
 * that extra would get it there.
 *
 * Money you will spend on your cards belongs in a piggy bank instead, and a
 * goal named like one says so.
 *
 * `onChanged` lets Ahead refresh: what goes to goals each month is what does
 * not go to investing.
 */
export default function Goals({ onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);

  async function load() {
    try {
      setData(await getGoals());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }
  useEffect(() => { load(); }, []);

  async function act(promise) {
    setError(null);
    try {
      setData(await promise);
      await onChanged?.();
      return true;
    } catch (e) {
      setError(e);
      return false;
    }
  }

  if (!data) return error ? <ErrorNote error={error} onRetry={load} /> : null;
  const goals = data.goals ?? [];
  const room = Math.max((data.saving ?? 0) - (data.to_goals ?? 0), 0);

  return (
    <Card title={<>Goals <span className="small muted" style={{ fontWeight: 500 }}>for keeping</span></>}
          actions={!adding && (
            <button className="btn" onClick={() => setAdding(true)}>+ New goal</button>
          )}>
      <ErrorNote error={error} />
      {data.over > 0 && (
        <p className="small" style={{ color: 'var(--critical)', marginTop: 0 }}>
          Goals take {money(data.over)} more a month than you save
        </p>
      )}

      {goals.length === 0 && !adding && (
        <div className="goal-empty">
          <div style={{ fontSize: '2rem' }} aria-hidden="true">🎯</div>
          <strong>What are you saving for?</strong>
          <span className="small muted">An emergency fund, a down payment, your first $10k.</span>
          <button className="btn primary" onClick={() => setAdding(true)}>
            Set a goal
          </button>
        </div>
      )}

      {adding && (
        <GoalForm initial={{ monthly: room ? String(Math.round(room)) : '' }}
                  submitLabel="Add goal" onTab={onTab}
                  onCancel={() => setAdding(false)}
                  onSubmit={async (fields) => {
                    if (await act(addGoal(fields))) setAdding(false);
                  }} />
      )}

      <div className="goal-list">
        {goals.map((g) => (
          <GoalItem key={g.id} goal={g} ahead={data.ahead} onTab={onTab}
                    onDeposit={(amount) => act(depositToGoal(g.id, amount))}
                    onEdit={(fields) => act(editGoal(g.id, fields))}
                    onDelete={() => act(deleteGoal(g.id))} />
        ))}
      </div>
    </Card>
  );
}

function GoalItem({ goal: g, ahead, onDeposit, onEdit, onDelete, onTab }) {
  const [mode, setMode] = useState(null);          // 'add' | 'edit' | null
  const [amount, setAmount] = useState('');
  const [party, setParty] = useState(false);

  // The first time a reached goal is seen on this device, a burst of confetti.
  useEffect(() => {
    if (g.reached && !celebrated().has(g.id)) {
      setParty(true);
      markCelebrated(g.id);
      const id = setTimeout(() => setParty(false), 2600);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [g.reached, g.id]);

  const pct = Math.round(g.progress * 100);

  return (
    <div className={`goal${g.reached ? ' reached' : ''}`}>
      {party && <Confetti />}
      <div className="goal-main">
        <Donut size={92} thickness={10} total={g.target}
               segments={[{ label: g.name, value: Math.max(g.saved, 0.0001),
                            color: g.reached ? 'var(--good)' : 'var(--ring-3)',
                            title: money(g.saved) }]}
               label={`${g.name}: ${pct}% of ${money(g.target)}`}>
          <div style={{ fontWeight: 720, fontSize: g.reached ? '1.4rem' : '1.05rem' }}>
            {g.reached ? '🎉' : `${pct}%`}
          </div>
        </Donut>
        <div className="goal-text">
          <strong>{g.name}</strong>
          <div className="num">
            {money(g.saved)} <span className="muted">of {money(g.target)}</span>
          </div>
          <div className="small muted">
            {g.reached
              ? `Reached ${monthLabel(g.reached_at?.slice(0, 7), { long: true })}`
              : g.eta
                ? `${monthLabel(g.eta, { long: true })} · ${money(g.monthly)}/mo`
                : 'Add a monthly amount to get a date'}
          </div>
          {!g.reached && g.sooner > 0 && ahead > 0 && (
            <div className="goal-boost">
              ✨ Your {money(ahead)} extra here → {g.sooner} month{g.sooner === 1 ? '' : 's'} sooner
            </div>
          )}
        </div>
      </div>

      {mode === 'add' ? (
        <form className="row goal-actions" onSubmit={async (e) => {
          e.preventDefault();
          if (!Number(amount)) return;
          await onDeposit(Number(amount));
          setAmount('');
          setMode(null);
        }}>
          <input type="number" step="any" inputMode="decimal" autoFocus
                 value={amount} onChange={(e) => setAmount(e.target.value)}
                 placeholder="Amount" aria-label={`Add money to ${g.name}`}
                 style={{ width: 120 }} />
          <button className="btn primary" type="submit">Add</button>
          <button className="btn quiet" type="button" onClick={() => setMode(null)}>
            Cancel
          </button>
        </form>
      ) : mode === 'edit' ? (
        <GoalForm initial={{ name: g.name, target: String(g.target),
                             saved: String(g.saved), monthly: String(g.monthly) }}
                  submitLabel="Save" onTab={onTab}
                  onCancel={() => setMode(null)}
                  onDelete={onDelete}
                  onSubmit={async (fields) => {
                    if (await onEdit(fields)) setMode(null);
                  }} />
      ) : (
        <div className="row goal-actions">
          {!g.reached && (
            <button className="btn" onClick={() => setMode('add')}>+ Add money</button>
          )}
          <button className="btn quiet" onClick={() => setMode('edit')}>Edit</button>
        </div>
      )}
    </div>
  );
}

function GoalForm({ initial, submitLabel, onSubmit, onCancel, onDelete, onTab }) {
  const [f, setF] = useState({ name: '', target: '', saved: '', monthly: '', ...initial });
  const set = (k) => (e) => setF((d) => ({ ...d, [k]: e.target.value }));

  return (
    <form className="goal-form" onSubmit={(e) => {
      e.preventDefault();
      onSubmit({ name: f.name, target: Number(f.target),
                 saved: Number(f.saved || 0), monthly: Number(f.monthly || 0) });
    }}>
      <label>Name
        <input value={f.name} onChange={set('name')} placeholder="Japan trip"
               maxLength={60} required />
      </label>
      <label>Target
        <input type="number" min="1" step="any" inputMode="decimal"
               value={f.target} onChange={set('target')} placeholder="4,000" required />
      </label>
      <label>Saved so far
        <input type="number" min="0" step="any" inputMode="decimal"
               value={f.saved} onChange={set('saved')} placeholder="0" />
      </label>
      <label>Each month
        <input type="number" min="0" step="any" inputMode="decimal"
               value={f.monthly} onChange={set('monthly')} placeholder="250" />
      </label>
      {soundsLikeSpending(f.name) && (
        <div className="goal-hint" style={{ gridColumn: '1 / -1' }}>
          <span>
            Spending this on your cards? A piggy bank pays for the charges, so
            they don't count against your weekly allowance.
          </span>
          {onTab && (
            <button className="btn" type="button" onClick={() => onTab('piggy')}>
              Make it a piggy bank
            </button>
          )}
        </div>
      )}
      <div className="row" style={{ gap: 8, gridColumn: '1 / -1' }}>
        {onDelete && (
          <button className="btn quiet" type="button" onClick={onDelete}
                  style={{ color: 'var(--critical)' }}>
            Delete
          </button>
        )}
        <span className="spacer" />
        <button className="btn quiet" type="button" onClick={onCancel}>Cancel</button>
        <button className="btn primary" type="submit">{submitLabel}</button>
      </div>
    </form>
  );
}

const COLOURS = ['var(--ring-1)', 'var(--ring-2)', 'var(--ring-3)', 'var(--ring-4)',
                 'var(--brand)', 'var(--warning)'];

/** A one-off burst, CSS only. */
function Confetti() {
  return (
    <div className="confetti" aria-hidden="true">
      {Array.from({ length: 28 }, (_, i) => (
        <span key={i} style={{
          left: `${(i * 37) % 100}%`,
          background: COLOURS[i % COLOURS.length],
          animationDelay: `${(i % 7) * 60}ms`,
          transform: `rotate(${i * 47}deg)`,
        }} />
      ))}
    </div>
  );
}
