import { useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, MonthFreshness, Notice, StatusPill,
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
 * of the daily number or budgeted monthly. The row is also where you change it.
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

  return (
    <div className="stack">
      {rows.length === 0 ? (
        <Card title="No budgets to show yet">
          <p className="muted">
            Budgets are worked out from the plan: what you take home, less your
            commitments and what you&apos;re saving, divided across categories
            in the proportions you already spend them. That way the total is a
            decision and only the split comes from your history.
          </p>
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
          {/* First, because every bar below it is drawn against a total that
              no longer matches the plan. Saying it after the bars would be
              letting the user read the wrong numbers first. */}
          {/* States the discrepancy without claiming why it exists. It can come
              from the plan moving underneath these budgets or from a category
              edited by hand here, and the notice has no way to tell which —
              asserting a cause it cannot know would be its own small untruth.
              The two directions do differ in how much they matter: allowing
              more than you have is misleading, allowing less is merely
              conservative. */}
          {nothingAdopted && (
            <Notice>
              <strong>
                None of these are budgets yet — they are what your plan would
                give each category, in the proportions you already spend.
              </strong>{' '}
              Adopt them in one go, or type over any line and save it on its
              own.
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn primary" onClick={adoptPlan}
                        disabled={applying}>
                  {applying ? 'Applying…' : "Use the plan's split"}
                </button>
                {onTab && (
                  <button className="btn quiet" onClick={() => onTab('plan')}>
                    See the plan first
                  </button>
                )}
              </div>
            </Notice>
          )}

          {drift && (
            <Notice kind={drift.gap > 0 ? 'error' : undefined}>
              <strong>
                These budgets divide {money(drift.saved_total)}; your plan has{' '}
                {money(drift.plan_total)}.
              </strong>{' '}
              {drift.gap > 0 ? (
                <>
                  So the lines below allow {money(drift.gap)} a month more than
                  you actually have
                  {drift.banks > 0 && (
                    <>, against {money(drift.banks)} a month now going into
                       piggy banks</>
                  )}
                  .
                </>
              ) : (
                <>
                  So {money(-drift.gap)} a month is left unassigned — not a
                  problem, but the plan has room these budgets do not use.
                </>
              )}
              <div className="row" style={{ marginTop: 12 }}>
                <button className={`btn${drift.gap > 0 ? ' primary' : ''}`}
                        onClick={adoptPlan} disabled={applying}>
                  {applying ? 'Applying…' : "Use the plan's split"}
                </button>
                {onTab && (
                  <button className="btn quiet" onClick={() => onTab('plan')}>
                    See the plan first
                  </button>
                )}
              </div>
            </Notice>
          )}

          <ErrorNote error={actionError} />

          {/* One wording for this, shared with Overview. */}
          <MonthFreshness month={month} summary={summary} onTab={onTab} />

          {/* Not worth saying when nothing is budgeted at all: the notice
              above already says that, and more usefully. */}
          {data.unbudgeted_spend > 1 && !nothingAdopted && (
            <Notice>
              <strong>
                {money(data.unbudgeted_spend)} of this month&apos;s{' '}
                {money(data.month_spend)} isn&apos;t covered by any budget line.
              </strong>{' '}
              The totals below only count categories you have a budget for, so
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
                hint="What each category has, how the month is going against it, and what the plan would give it"
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
            <p className="assumption" style={{ marginBottom: 0 }}>
              Set a category to 0 to remove its budget. The shares come from how
              you already divide your spending, so the budget fits the way you
              actually live; the total does not — it comes from the plan, which
              is the only way a budget can ever ask for less than last month.
            </p>
          </Card>
        </>
      )}
    </div>
  );
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
            to be on the page, per category. Which categories those are was
            decided by a table in categorize.py that the app showed nowhere. */}
        <span className="small muted">
          {row.essential ? 'budgeted monthly' : 'in the daily number'}
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
              ? `Projected ${money(row.projected)} by month end — ${money(row.remaining)} left.`
              : `Projected ${money(row.projected)} by month end, ${money(Math.abs(row.projected_over))} over.`
          ) : (
            `Not budgeted yet — drawn against the ${money(row.budget)} the plan would give it.`
          )}
          {differs && (
            <>
              {' '}Plan says{' '}
              {/* Worth colouring only when the saved figure is the larger one
                  — that is the direction that tells someone they have more to
                  spend than they do. */}
              <span className={over ? 'num' : 'num muted'}
                    style={over ? { color: 'var(--critical)' } : undefined}>
                {money(row.plan_budget)}
              </span>.
            </>
          )}
          {row.typical ? ` You usually spend ${money(row.typical)}.` : ''}
        </span>
        <span className="spacer" />
        <label className="small muted" htmlFor={`budget-${row.category}`}>
          Budget
        </label>
        <input
          id={`budget-${row.category}`}
          type="number"
          min="0"
          step="10"
          style={{ width: 110, textAlign: 'right' }}
          value={draft ?? (row.adopted ? row.budget : '')}
          placeholder={row.plan_budget != null ? String(row.plan_budget) : '0'}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={`${row.category} monthly budget`}
        />
      </div>
    </div>
  );
}
