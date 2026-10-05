import { useEffect, useState } from 'react';
import {
  Card, ErrorNote, GoTo, Loading, NoticeStack, StatusPill, freshness,
} from '../components/ui.jsx';
import {
  applyPlanBudgets, getBudgets, money, monthLabel, pct, setBudgets,
} from '../api.js';

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
 * Every category, once.
 *
 * This page used to be two tables, with a third on the Plan tab: bars here,
 * an editor below them, and the plan's proposed split over there — three
 * renderings of one list, two of them editable. Which figure you were looking
 * at depended on which card you had scrolled to, and the reasonable conclusion
 * was that the app had several budgets.
 *
 * So there is one row per category now, and it carries everything the three
 * used to say separately: what you have set, what the plan would give it, what
 * you usually spend, how the month is going against it, and whether it is part
 * of the weekly number or budgeted monthly. The row is also where you change it.
 */
export default function BudgetsPanel({ month, summary, onTab, version = 0 }) {
  const [data, setData] = useState(null);
  // Two error slots, not one. A failed load has nothing to show, so it replaces
  // the panel; a failed save has to leave the table and the half-typed draft
  // exactly where they were, or a transient failure costs the user their edits.
  const [loadError, setLoadError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);

  async function load() {
    setLoadError(null);
    try {
      setData(await getBudgets(month));
    } catch (e) {
      setLoadError(e);
    }
  }

  // `version` changes on an import, which changes what has been spent.
  useEffect(() => { load(); }, [month, version]);

  async function save() {
    setSaving(true);
    setActionError(null);
    try {
      await setBudgets(draft);
      setDraft({});
      await load();
    } catch (e) {
      setActionError(e);          // the draft survives on purpose
    } finally {
      setSaving(false);
    }
  }

  async function adoptPlan() {
    setApplying(true);
    setActionError(null);
    try {
      await applyPlanBudgets();
      setDraft({});
      await load();
    } catch (e) {
      setActionError(e);
    } finally {
      setApplying(false);
    }
  }

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data) return <Loading what="budgets" />;

  // Saved budgets and the plan's proposals in one list, from the server, so a
  // category the plan pays for is on the page before it has a budget.
  const rows = data.rows ?? [];
  const drift = data.drift;
  const edited = Object.keys(draft).length > 0;
  // Every line is a proposal and none of them has been adopted. There is no
  // drift to report in that state — nothing is saved to drift from — so
  // without this the page showed a full table and no way to accept it.
  const nothingAdopted = rows.length > 0 && rows.every((r) => !r.adopted);

  const planButtons = (primary) => (
    <div className="row" style={{ marginTop: 12 }}>
      <button className={`btn${primary ? ' primary' : ''}`}
              onClick={adoptPlan} disabled={applying}>
        {applying ? 'Applying…' : "Use the plan's split"}
      </button>
      {onTab && (
        <button className="btn quiet" onClick={() => onTab('plan')}>
          Plan
        </button>
      )}
    </div>
  );

  // Everything this page needs to say before the table, as one strip: the
  // most serious in full, the rest a line each. It used to be up to five
  // notices stacked above the first category. Rank: 0 is something wrong
  // with the figures, 1 something to do, 2 something to know.
  const notices = [
    // Budgets that no longer divide the money the plan has. States the
    // discrepancy without claiming why — it can come from the plan moving or
    // from a line edited by hand, and the page cannot tell which. Allowing
    // more than you have is wrong; allowing less is merely conservative.
    drift && {
      key: 'drift',
      kind: drift.gap > 0 ? 'error' : '',
      rank: drift.gap > 0 ? 0 : 2,
      summary: <>Budgets {money(drift.saved_total)} · plan {money(drift.plan_total)}</>,
      detail: planButtons(drift.gap > 0),
    },
    data.bank_funded && bankFundedItem(data.bank_funded, onTab),
    nothingAdopted && {
      key: 'adopt', kind: '', rank: 1,
      summary: <>Not adopted yet</>,
      detail: planButtons(true),
    },
    // One wording for this, shared with This month.
    (() => {
      const it = freshness(month, summary, { onTab, from: 'budgets' });
      return it && { ...it, rank: 2 };
    })(),
    // Not worth saying when nothing is budgeted at all: the adopt notice
    // already says that, and more usefully.
    data.unbudgeted_spend > 1 && !nothingAdopted && {
      key: 'unbudgeted', kind: '', rank: 2,
      summary: <>{money(data.unbudgeted_spend)} not in any budget</>,
      detail: data.unbudgeted?.length > 0 ? (
        <span className="muted">
          {data.unbudgeted.slice(0, 5).map((r) => r.category).join(', ')}
          {data.unbudgeted.length > 5 && ` +${data.unbudgeted.length - 5}`}
        </span>
      ) : null,
    },
  ].filter(Boolean).sort((a, b) => a.rank - b.rank);

  return (
    <div className="stack">
      {rows.length === 0 ? (
        <Card title="No budgets to show yet">
          {/* It used to send you to the Plan tab to press a button there. The
              button belongs on the page that is empty without it. */}
          <ErrorNote error={actionError} />
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={adoptPlan} disabled={applying}>
              {applying ? 'Applying…' : "Use the plan's split"}
            </button>
            {onTab && (
              <button className="btn quiet" onClick={() => onTab('plan')}>
                Set up the plan first
              </button>
            )}
          </div>
        </Card>
      ) : (
        <>
          {/* A failure to save is live, so it is never folded into the strip. */}
          <ErrorNote error={actionError} />

          <NoticeStack items={notices} />

          <Card title={`Budgets — ${monthLabel(month, { long: true })}`}
                actions={(
                  <div className="row" style={{ gap: 8 }}>
                    {edited && (
                      <button className="btn quiet" onClick={() => setDraft({})}>
                        Discard
                      </button>
                    )}
                    <button className="btn primary" onClick={save}
                            disabled={saving || !edited}>
                      {saving ? 'Saving…' : 'Save changes'}
                    </button>
                  </div>
                )}>
            <div className="stack" style={{ gap: 22 }}>
              {rows.map((r) => (
                <BudgetRow key={r.category} row={r}
                           draft={draft[r.category]}
                           onChange={(v) => setDraft((d) => ({
                             ...d, [r.category]: v,
                           }))} />
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

/**
 * Why some categories are not in the table: a piggy bank pays for them.
 *
 * Normally one quiet line saying which bank. The one other state is spending
 * in those categories from before the bank opened, which the bank does not
 * pay for and so still counts in its month.
 */
function bankFundedItem(banked, onTab) {
  const list = banked.categories;
  if (!list?.length) return null;
  const names = joinNames(list);
  const left = banked.unallocated_total;
  const payers = banked.paid_by ?? [];

  if (left > 1) {
    return {
      key: 'banked', kind: '', rank: 1,
      summary: <>{money(left)} of {names.toLowerCase()} before its bank opened</>,
      detail: null,
    };
  }

  return {
    key: 'banked', kind: 'good', rank: 2,
    summary: payers.length > 0
      ? <>{payers.map((p, i) => (
          <span key={p.id}>
            {i > 0 && '; '}
            {joinNames(p.categories)} → {p.bank} bank
          </span>
        ))}</>
      : <>{names} → piggy bank</>,
    detail: null,
  };
}

function joinNames(list) {
  return list.length > 1
    ? `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`
    : list[0];
}

/**
 * One category: the bar, the editor, and the two reference figures.
 *
 * A row the plan proposes but nothing has adopted is shown the same way, drawn
 * against the plan's figure, with the input left empty — it is a suggestion
 * until someone types in it, and an input pre-filled with a number nobody
 * chose reads as a budget that exists.
 */
function BudgetRow({ row, draft, onChange }) {
  const s = state(row);
  const used = Math.min(row.used, 1);
  const colour = row.adopted ? s : 'warning';
  // Only worth saying when the two differ. Printing "plan says $78" against a
  // budget of $78 on every row is noise that hides the one row where it is
  // $78 against $120.
  const differs = row.adopted && row.plan_budget != null
    && Math.abs(row.budget - row.plan_budget) > 1;
  const over = differs && row.budget > row.plan_budget;

  return (
    <div>
      <div className="row" style={{ marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <strong>{row.category}</strong>
        {row.adopted
          ? <StatusPill state={s}>{STATE_TEXT[s]}</StatusPill>
          : <StatusPill state="warning">No budget set</StatusPill>}
        {/* The answer to "where does the discretionary figure come from" has
            to be on the page, per line. A line folded from several
            categories can be partly in it — Health is budgeted monthly,
            Personal Care is in the weekly number — and says so. */}
        <span className="small muted">
          {{ all: 'weekly', none: 'monthly', part: 'partly weekly' }[row.daily]
            ?? (row.essential ? 'monthly' : 'weekly')}
        </span>
        <span className="spacer" />
        <span className="num small">
          {money(row.spent, { cents: true })}
          {row.adopted ? (
            <> of {money(row.budget)}{' '}
              <span className="muted">({pct(row.used)})</span>
            </>
          ) : <> spent</>}
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
          background: `var(--${colour === 'good' ? 'good' : colour})`,
        }} />
      </div>

      <div className="row" style={{ marginTop: 7, flexWrap: 'wrap', gap: 8 }}>
        <span className="small muted">
          {row.adopted ? (
            row.on_track
              ? `${money(row.projected)} projected · ${money(row.remaining)} left`
              : `${money(row.projected)} projected · ${money(Math.abs(row.projected_over))} over`
          ) : (
            `Plan ${money(row.budget)}`
          )}
          {differs && (
            <>
              {' '}· plan{' '}
              {/* Worth colouring only when the saved figure is the larger one
                  — that is the direction that tells someone they have more to
                  spend than they do. */}
              <span className={over ? 'num' : 'num muted'}
                    style={over ? { color: 'var(--critical)' } : undefined}>
                {money(row.plan_budget)}
              </span>
            </>
          )}
          {row.typical ? ` · usually ${money(row.typical)}` : ''}
        </span>
        <span className="spacer" />
        <label className="small muted" htmlFor={`budget-${row.category}`}>
          Budget
        </label>
        <input
          id={`budget-${row.category}`}
          type="number"
          min="0"
          step="any"
          style={{ width: 110, textAlign: 'right' }}
          // Whole dollars, like the bar beside it — "$693" above an input
          // reading 692.73 looked like two different figures. Only an edited
          // line is saved, so a stored figure with cents is left exactly as
          // it is unless you change it.
          value={draft ?? (row.adopted ? Math.round(row.budget) : '')}
          placeholder={row.plan_budget != null
            ? String(Math.round(row.plan_budget)) : '0'}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={`${row.category} monthly budget`}
        />
      </div>
    </div>
  );
}
