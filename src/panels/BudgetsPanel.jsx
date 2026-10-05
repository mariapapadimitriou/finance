import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, StatusPill } from '../components/ui.jsx';
import { getBudgets, money, monthLabel, pct, setAllocation } from '../api.js';

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

/**
 * Budgets: you split the monthly total yourself.
 *
 * The plan works out one figure — what is left after pay, commitments, saving
 * and piggy banks. Here you pick the categories you want to keep an eye on,
 * give each a monthly target, and everything together has to add up to that
 * figure. The rest sit under "Other categories" at 0 unless you give them
 * something. The lines are the ones in Settings → Categories.
 *
 * Three steps, the first two only while setting up or changing it:
 * pick (which lines to focus on), split (the amounts), track (the month).
 */
export default function BudgetsPanel({ month, summary, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [mode, setMode] = useState(null);         // 'pick' | 'split' | 'track'
  const [focus, setFocus] = useState([]);
  const [draft, setDraft] = useState({});

  async function load() {
    setLoadError(null);
    try {
      const d = await getBudgets(month);
      setData(d);
      setMode((m) => m ?? (d.focus ? 'track' : 'pick'));
    } catch (e) {
      setLoadError(e);
    }
  }

  // `version` changes on an import, which changes what has been spent.
  useEffect(() => { load(); }, [month, version]);

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data || !mode) return <Loading what="budgets" />;

  const rows = data.rows ?? [];

  // Start (or restart) choosing, from what is saved.
  function startPick() {
    setFocus(data.focus ?? []);
    setMode('pick');
  }
  function startSplit(chosen) {
    const next = {};
    rows.forEach((r) => {
      if (r.adopted) next[r.category] = String(Math.round(r.budget * 100) / 100);
      else if (!chosen.includes(r.category)) next[r.category] = '0';
    });
    setFocus(chosen);
    setDraft(next);
    setMode('split');
  }

  if (data.monthly_total == null || data.monthly_total <= 0) {
    return (
      <Card title="Finish your plan first">
        <p className="muted" style={{ marginTop: 0 }}>
          Your monthly total is what's left of your take-home pay after
          commitments, saving and piggy banks. Budgets split it up.
        </p>
        {onTab && (
          <button className="btn primary" onClick={() => onTab('plan')}>
            Go to Income
          </button>
        )}
      </Card>
    );
  }

  if (mode === 'pick') {
    return (
      <PickFocus rows={rows} initial={data.focus ?? focus}
                 canCancel={!!data.focus}
                 onCancel={() => setMode('track')}
                 onNext={(chosen) => startSplit(chosen)} />
    );
  }

  if (mode === 'split') {
    return (
      <SplitTotal rows={rows} total={data.monthly_total} focus={focus}
                  draft={draft} setDraft={setDraft}
                  onBack={() => setMode('pick')}
                  onCancel={data.focus ? () => setMode('track') : null}
                  onSaved={async () => { await load(); setMode('track'); }} />
    );
  }

  return (
    <Track data={data} month={month} onTab={onTab}
           onEdit={() => startSplit(data.focus ?? [])}
           onFocus={startPick} />
  );
}

/** Step one: which lines to keep an eye on. */
function PickFocus({ rows, initial, canCancel, onCancel, onNext }) {
  const [chosen, setChosen] = useState(() => new Set(initial));
  const toggle = (name) => setChosen((s) => {
    const next = new Set(s);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });

  return (
    <Card title="What do you want to focus on?"
          actions={canCancel && (
            <button className="btn quiet" onClick={onCancel}>Cancel</button>
          )}>
      <p className="muted small" style={{ marginTop: 0 }}>
        Pick the categories to track closely. You'll give each one a monthly
        target next. The rest go under Other categories.
      </p>
      <div className="stack" style={{ gap: 4 }}>
        {rows.map((r) => (
          <label key={r.category} className="row"
                 style={{ gap: 10, padding: '8px 0', cursor: 'pointer', flexWrap: 'wrap' }}>
            <input type="checkbox" checked={chosen.has(r.category)}
                   onChange={() => toggle(r.category)} />
            <div style={{ minWidth: 0 }}>
              <strong>{r.category}</strong>
              {r.members?.length > 0 && (
                <div className="small muted">{r.members.join(' · ')}</div>
              )}
            </div>
            <span className="spacer" />
            <History row={r} />
          </label>
        ))}
      </div>
      <div className="row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
        <button className="btn primary" disabled={chosen.size === 0}
                onClick={() => onNext(rows.map((r) => r.category)
                  .filter((c) => chosen.has(c)))}>
          Next{chosen.size > 0 ? ` (${chosen.size})` : ''}
        </button>
      </div>
    </Card>
  );
}

/** Step two: the amounts, which have to add up to the monthly total. */
function SplitTotal({ rows, total, focus, draft, setDraft, onBack, onCancel, onSaved }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const focusRows = rows.filter((r) => focus.includes(r.category));
  const otherRows = rows.filter((r) => !focus.includes(r.category));
  const blank = (name) => draft[name] === undefined || draft[name] === ''
    || Number.isNaN(Number(draft[name]));
  const value = (name) => (blank(name) ? 0 : Number(draft[name]));
  const allocated = rows.reduce((t, r) => t + value(r.category), 0);
  const left = Math.round((total - allocated) * 100) / 100;
  const missing = focusRows.filter((r) => blank(r.category));
  const otherTotal = otherRows.reduce((t, r) => t + value(r.category), 0);
  const ready = missing.length === 0 && Math.abs(left) <= 0.5;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const budgets = {};
      rows.forEach((r) => {
        if (!blank(r.category)) budgets[r.category] = Number(draft[r.category]);
      });
      await setAllocation(focus, budgets);
      await onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  const input = (r) => (
    <input
      id={`budget-${r.category}`}
      type="number" min="0" step="any" inputMode="decimal"
      style={{ width: 110, textAlign: 'right' }}
      value={draft[r.category] ?? ''}
      placeholder={focus.includes(r.category) ? '' : '0'}
      onChange={(e) => setDraft((d) => ({ ...d, [r.category]: e.target.value }))}
      aria-label={`${r.category} monthly budget`}
    />
  );

  return (
    <Card title="Split your monthly total"
          actions={onCancel && (
            <button className="btn quiet" onClick={onCancel}>Cancel</button>
          )}>
      <div className="row" style={{ gap: 12, alignItems: 'flex-end' }}>
        <div>
          <div className="small muted">Monthly total</div>
          <div className="num" style={{ fontSize: '1.5rem', fontWeight: 650 }}>
            {money(total, { cents: true })}
          </div>
        </div>
        <span className="spacer" />
        <div style={{ textAlign: 'right' }}>
          <div className="small muted">
            {left > 0.5 ? 'Left to assign' : left < -0.5 ? 'Too much' : 'All assigned'}
          </div>
          <div className="num" style={{
            fontSize: '1.5rem', fontWeight: 650,
            color: left < -0.5 ? 'var(--critical)'
              : Math.abs(left) <= 0.5 ? 'var(--good-text)' : undefined,
          }}>
            {money(Math.abs(left), { cents: true })}
          </div>
        </div>
      </div>

      <div className="stack" style={{ gap: 14, marginTop: 16 }}>
        {focusRows.map((r) => (
          <div key={r.category} className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
            <div style={{ minWidth: 0 }}>
              <strong>{r.category}</strong>
              <div><History row={r} /></div>
            </div>
            <span className="spacer" />
            {input(r)}
          </div>
        ))}
      </div>

      {otherRows.length > 0 && (
        <details className="evidence" style={{ marginTop: 18 }}>
          <summary>
            Other categories
            <span className="muted num" style={{ fontWeight: 400 }}>
              {' '}· {money(otherTotal)}
            </span>
          </summary>
          <div className="stack" style={{ gap: 12, marginTop: 12 }}>
            {otherRows.map((r) => (
              <div key={r.category} className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <span>{r.category}</span>
                  <div><History row={r} /></div>
                </div>
                <span className="spacer" />
                {input(r)}
              </div>
            ))}
          </div>
        </details>
      )}

      <ErrorNote error={error} />
      <div className="row" style={{ marginTop: 16, gap: 8, flexWrap: 'wrap' }}>
        <button className="btn quiet" onClick={onBack}>Back</button>
        <span className="spacer" />
        {missing.length > 0 && (
          <span className="small muted">
            {missing.length === 1
              ? `${missing[0].category} needs a target`
              : `${missing.length} categories need a target`}
          </span>
        )}
        <button className="btn primary" onClick={save} disabled={!ready || saving}>
          {saving ? 'Saving…' : 'Save budgets'}
        </button>
      </div>
    </Card>
  );
}

/** Step three: the month against the targets. */
function Track({ data, month, onTab, onEdit, onFocus }) {
  const rows = data.rows ?? [];
  const focusRows = rows.filter((r) => r.focus);
  const otherRows = rows.filter((r) => !r.focus);
  const bankLines = data.bank_lines ?? [];
  const other = data.other ?? { spent: 0, budget: 0 };
  const otherOver = other.spent > other.budget;

  return (
    <div className="stack">
      <Card title={`Budgets — ${monthLabel(month, { long: true })}`}
            actions={(
              <div className="row" style={{ gap: 8 }}>
                <button className="btn quiet" onClick={onFocus}>Focus</button>
                <button className="btn" onClick={onEdit}>Edit budgets</button>
              </div>
            )}>
        <div className="stack" style={{ gap: 22 }}>
          {focusRows.map((r) => <BudgetRow key={r.category} row={r} />)}
        </div>

        {otherRows.length > 0 && (
          <details className="evidence" style={{ marginTop: 22 }}>
            <summary>
              Other categories
              <span className="num" style={{
                fontWeight: 400,
                color: otherOver ? 'var(--critical)' : 'var(--muted)',
              }}>
                {' '}· {money(other.spent)} of {money(other.budget)}
              </span>
            </summary>
            <div className="stack" style={{ gap: 10, marginTop: 12 }}>
              {otherRows.map((r) => (
                <div key={r.category} className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
                  <span>{r.category}</span>
                  <span className="spacer" />
                  <span className="num small"
                        style={r.spent > r.budget ? { color: 'var(--critical)' } : undefined}>
                    {money(r.spent, { cents: true })} of {money(r.budget)}
                  </span>
                </div>
              ))}
            </div>
          </details>
        )}

        {bankLines.length > 0 && (
          <div className="stack" style={{
            gap: 10, marginTop: 18, paddingTop: 14,
            borderTop: '1px solid var(--border)',
          }}>
            {bankLines.map((l) => (
              <div key={l.category}>
                <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
                  <strong>{l.category}</strong>
                  <span className="small muted">
                    Paid by {l.bank ? `${l.bank} bank` : 'a piggy bank'}
                  </span>
                  <span className="spacer" />
                  {l.uncovered > 1 && (
                    <span className="num small">
                      {money(l.uncovered, { cents: true })} not covered
                    </span>
                  )}
                </div>
                {l.members?.length > 0 && (
                  <div className="small muted">{l.members.join(' · ')}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {onTab && (
          <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
            <button className="btn quiet" onClick={() => onTab('categories')}>
              Edit lines
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}

/** "avg $X · median $Y": your own months, the guide beside a target. */
function History({ row }) {
  if (!row.average && !row.median) return <span className="small muted">no history</span>;
  return (
    <span className="small muted num">
      avg {money(row.average)} · median {money(row.median)}
    </span>
  );
}

/** One focus line: how the month is going against its target. */
function BudgetRow({ row }) {
  const s = state(row);
  const used = row.budget > 0 ? Math.min(row.used, 1) : (row.spent > 0 ? 1 : 0);

  return (
    <div>
      <div className="row" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <strong>{row.category}</strong>
        <StatusPill state={s}>{STATE_TEXT[s]}</StatusPill>
        {/* Which side of the weekly number this line is on. A line folded
            from several categories can be partly in it, and says so. */}
        <span className="small muted">
          {{ all: 'weekly', none: 'monthly', part: 'partly weekly' }[row.daily]
            ?? (row.essential ? 'monthly' : 'weekly')}
        </span>
        <span className="spacer" />
        <span className="num small">
          {money(row.spent, { cents: true })} of {money(row.budget)}
          {row.budget > 0 && <span className="muted"> ({pct(row.used)})</span>}
        </span>
      </div>

      {row.members?.length > 0 && (
        <div className="small muted" style={{ marginTop: -4, marginBottom: 8 }}>
          {row.members.join(' · ')}
        </div>
      )}

      <div className="track" style={{
        background: 'var(--surface-2)', borderRadius: 4,
        height: 8, overflow: 'hidden',
      }}>
        <div style={{
          width: `${used * 100}%`,
          height: '100%',
          borderRadius: '0 4px 4px 0',
          background: `var(--${s})`,
        }} />
      </div>

      <div className="row" style={{ marginTop: 7, flexWrap: 'wrap', gap: 8 }}>
        <span className="small muted">
          {row.on_track
            ? `${money(row.projected)} projected · ${money(row.remaining)} left`
            : `${money(row.projected)} projected · ${money(Math.abs(row.projected_over))} over`}
        </span>
        <span className="spacer" />
        <History row={row} />
      </div>
    </div>
  );
}
