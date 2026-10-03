import { useEffect, useState } from 'react';
import {
  Card, ErrorNote, GoTo, Loading, NoticeStack, StatusPill, Why, freshness,
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
          See the plan first
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
      summary: <>These budgets divide {money(drift.saved_total)}; your plan
        has {money(drift.plan_total)}.</>,
      detail: drift.gap > 0 ? (
        <>
          So the lines below allow {money(drift.gap)} a month more than you
          actually have{drift.banks > 0 && (
            <>, against {money(drift.banks)} a month now going into piggy
               banks</>
          )}.
          {planButtons(true)}
        </>
      ) : (
        <>
          So {money(-drift.gap)} a month is left unassigned — not a problem,
          but the plan has room these budgets do not use.
          {planButtons(false)}
        </>
      ),
    },
    data.bank_funded && bankFundedItem(data.bank_funded, onTab),
    nothingAdopted && {
      key: 'adopt', kind: '', rank: 1,
      summary: <>None of these are budgets yet — they are what your plan would
        give each line, in the proportions you already spend.</>,
      detail: <>Adopt them in one go, or type over any line and save it on its
        own.{planButtons(true)}</>,
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
      summary: <>{money(data.unbudgeted_spend)} of this month&apos;s{' '}
        {money(data.budgetable_spend)} isn&apos;t covered by any budget
        line.</>,
      detail: (
        <>
          The totals below only count lines you have a budget for, so they
          will always read lower than{' '}
          <GoTo to="overview" from="budgets" onTab={onTab} /> until everything
          has one.{data.unbudgeted?.length > 0 && (
            <> Missing:{' '}
              {data.unbudgeted.slice(0, 5).map((r) => r.category).join(', ')}
              {data.unbudgeted.length > 5
                && ` and ${data.unbudgeted.length - 5} more`}.</>
          )}
        </>
      ),
    },
  ].filter(Boolean).sort((a, b) => a.rank - b.rank);

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
          {/* A failure to save is live, so it is never folded into the strip. */}
          <ErrorNote error={actionError} />

          <NoticeStack items={notices} />

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
            {/* The instruction stays; the reasoning folds. */}
            <p className="small muted" style={{ margin: '16px 0 0' }}>
              Set a line to 0 to remove its budget.
            </p>
            <Why id="budgets.shares" label="Where do these figures come from?">
              The shares come from how you already divide your spending, so the
              budget fits the way you actually live; the total does not — it
              comes from the plan, which is the only way a budget can ever ask
              for less than last month.
            </Why>
          </Card>
        </>
      )}
    </div>
  );
}

/**
 * Why Travel is not in the table, and what that leaves outstanding.
 *
 * Three states worth distinguishing: no bank at all, which means the cost is
 * funded by nothing; a bank that covered everything, which is the system
 * working and needs one quiet line; and a bank that did not cover a charge,
 * which is money still coming out of this month until it is allocated.
 */
function bankFundedItem(banked, onTab) {
  // One line or several — the set is a decision in categorize.py and in your
  // grouping, not a constant this function gets to assume the size of.
  const list = banked.categories;
  if (!list?.length) return null;
  const names = list.length > 1
    ? `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`
    : list[0];
  const verb = list.length > 1 ? 'have' : 'has';
  const left = banked.unallocated_total;

  if (banked.banks === 0) {
    return {
      key: 'banked', kind: 'error', rank: 0,
      summary: <>{names} {verb} no budget line and no piggy bank.</>,
      detail: (
        <>
          {list.length > 1 ? 'They are' : 'It is'} left out of the split below
          on purpose — a cost that arrives in lumps is wrong as a monthly line
          — on the understanding that a bank is collecting for{' '}
          {list.length > 1 ? 'them' : 'it'}. Nothing is.
          {onTab && (
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" onClick={() => onTab('piggy')}>
                Open a travel bank
              </button>
            </div>
          )}
        </>
      ),
    };
  }

  if (left <= 1) {
    return {
      key: 'banked', kind: 'good', rank: 2,
      summary: <>{names} {verb === 'have' ? 'are' : 'is'} paid for by a piggy
        bank, not budgeted.</>,
      detail: <>That is why there is no line below for{' '}
        {list.length > 1 ? 'them' : 'it'}, and nothing this month is waiting
        to be charged to a bank.</>,
    };
  }

  return {
    key: 'banked', kind: '', rank: 1,
    summary: <>{money(left)} of {names.toLowerCase()} this month isn&apos;t
      charged to a piggy bank.</>,
    detail: (
      <>
        {names} {verb} no budget line — a bank funds{' '}
        {list.length > 1 ? 'them' : 'it'} instead — so until that charge is
        allocated to one it comes out of this month like any other spending.
        Charge it in <GoTo to="transactions" from="budgets" onTab={onTab} />{' '}
        and it leaves the month entirely.
      </>
    ),
  };
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
          {{ all: 'in the weekly number', none: 'budgeted monthly',
             part: 'partly in the weekly number' }[row.daily]
            ?? (row.essential ? 'budgeted monthly' : 'in the weekly number')}
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
