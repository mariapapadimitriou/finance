import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getCategoryBudgets, putCategoryBudget } from '../api.js';
import { DetailPanel, PButton, Segmented } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { SnapshotBar } from '../pearl/viz.jsx';
import { longDate, monthName, shown } from './HomePanel.jsx';
import { GrowthTabs } from './InsightsParts.jsx';
import { LensToggle, readLens, writeLens } from './Lens.jsx';
import './home.css';

/**
 * Budgets (THL-168, designed in THL-185): B-01 every category's budget under
 * Growth, B-02 changing one as a share of usual, B-03 the card on Home.
 *
 * Each budget starts at her usual month for the category, so there's nothing
 * to fill in, and changes as a percent of usual with the dollars beside it:
 * 70% to 110%, or a custom 50% to 150% in 5% steps (B3). Rows are the
 * snapshot's bar against the budget, so the ±10% pace rule and the champagne
 * for over are the same (B1): on track, on pace to go over, or over, always
 * in words. A category that's all bills has no tick and says "All paid" once
 * they're in (B2). Budgets sit under Allowance; they don't replace it.
 */

export const PRESETS = [70, 80, 90, 100, 110];
export const CUSTOM = { min: 50, max: 150, step: 5 };

/** A budget in dollars: usual × pct, to the cent below. */
export const budgetFor = (usual, pct) => Math.floor(Math.round(usual * 100) * pct / 100) / 100;

/** The SnapshotBar props for one budget row (B-01). Whole dollars, no $0. */
export function budgetBar(r, data) {
  const month = monthName(data.month);
  const category = `${r.category} · ${r.pct}% of usual`;
  const value = r.spent > 0 ? `${shown(r.spent)} of ${shown(r.budget)}` : `Nothing yet of ${shown(r.budget)}`;
  const overWords = r.over_by ? `${shown(r.over_by)} over this month` : 'Over this month';
  if (r.bill) {
    return {
      category, value, share: r.budget > 0 ? r.spent / r.budget : 0, over: r.status === 'over-month',
      note: r.status === 'over-month' ? overWords
        : r.status === 'to_come' ? `${shown(r.to_come)} still to come this month`
          : `All paid for ${month}`,
    };
  }
  return {
    category, value, spent: r.spent, usualMonth: r.budget, usualByToday: r.by_today,
    day: data.day, daysInMonth: data.days_in_month, monthsOfHistory: data.months_of_history,
    note: (status) => (status === 'over-month' ? overWords
      : status === 'over' ? 'On pace to go over' : 'On track'),
  };
}

/** What changing a budget does, in words (B-02). */
export function changeWords(usual, pct) {
  const diff = Math.abs(usual - budgetFor(usual, pct));
  if (pct === 100 || diff < 1) return 'The same as your usual month. You can change it any time.';
  return `About ${shown(diff)} ${pct < 100 ? 'less' : 'more'} than usual. You can change it any time.`;
}

/** B-03: on Home only when a budget needs a look (B4). */
export function BudgetsCard({ budgets, onSee }) {
  const n = budgets?.needs_look ?? 0;
  if (!budgets?.ready || n < 1) return null;
  return (
    <section className="hm-card" aria-labelledby="hm-budgets-title">
      <h2 className="pk-h3" id="hm-budgets-title">Budgets</h2>
      <p className="pk-muted">{n === 1 ? '1 budget needs a look this month.' : `${n} budgets need a look this month.`}</p>
      <button type="button" className="hm-link" onClick={onSee}>
        See budgets <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

export default function CategoryBudgetsPanel({ onTab, onChanged, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getCategoryBudgets().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your budgets…</p></div>;
  const row = editing && data.rows.find((r) => r.category === editing);
  return (
    <BudgetsPage data={data} onChange={setEditing} onTab={onTab}>
      {row && (
        <ChangeBudget row={row} onClose={() => setEditing(null)}
                      onSave={(pct) => putCategoryBudget(row.category, pct).then((next) => {
                        setData(next);
                        setEditing(null);
                        onChanged?.();
                      })} />
      )}
    </BudgetsPage>
  );
}

/** B-01: every budget this month, the five largest first. */
export function BudgetsPage({ data, onChange, onTab, children = null }) {
  const [all, setAll] = useState(false);
  const [lens, setLensState] = useState(readLens);
  const setLens = (l) => { setLensState(l); writeLens(l); };
  const month = monthName(data.month);
  const top = data.rows.slice(0, data.top ?? 5);
  const rest = data.rows.slice(data.top ?? 5);
  // By kind: the bills first, then everything decided week by week.
  const shown = all ? data.rows : top;
  const sections = lens === 'kind'
    ? [{ key: 'fixed', label: 'Fixed', rows: shown.filter((r) => r.bill) },
       { key: 'variable', label: 'Variable', rows: shown.filter((r) => !r.bill) }].filter((s) => s.rows.length)
    : [{ key: 'all', label: null, rows: shown }];
  return (
    <div className="pk hm-page bd-page">
      <header className="hm-head">
        <p className="pk-overline accent">Budgets</p>
        <h1 className="pk-h1">Cash flow</h1>
      </header>
      <GrowthTabs current="budgets" onTab={onTab} />
      <div className="hm-row-between">
        <h2 className="pk-h2">{`Budgets for ${month}`}</h2>
        {data.ready && data.rows.length > 0 && <LensToggle lens={lens} onChange={setLens} />}
      </div>
      {!data.ready ? (
        <section className="hm-card">
          <h2 className="pk-h3">Budgets start after your first full month</h2>
          <p className="pk-muted">
            {data.starts
              ? `Each budget starts at your usual month for that category, so they begin on ${longDate(data.starts)}.`
              : 'Each budget starts at your usual month for that category, so they begin once we’ve seen a full month.'}
          </p>
        </section>
      ) : data.rows.length === 0 ? (
        <section className="hm-card">
          <h2 className="pk-h3">No spending to budget yet</h2>
          <p className="pk-muted">Budgets appear here for every category you usually spend on.</p>
        </section>
      ) : (
        <section className="hm-card bd-list" aria-label={`Budgets for ${month}`}>
          <p className="pk-muted">
            Each budget starts at your usual month for that category. Change any of them as a share of usual.
          </p>
          {sections.map((s) => (
            <div key={s.key} className="bd-section">
              {s.label && <h3 className="pk-overline">{s.label}</h3>}
              {s.rows.map((r) => (
                <div key={r.category} className="bd-row">
                  <div className="bd-bar"><SnapshotBar {...budgetBar(r, data)} showTick={!r.bill} /></div>
                  <button type="button" className="hm-link bd-change" onClick={() => onChange(r.category)}
                          aria-label={`Change the ${r.category} budget`}>
                    Change <PIcon name="chevronRight" size={14} />
                  </button>
                </div>
              ))}
            </div>
          ))}
          {rest.length > 0 && (
            <button type="button" className="hm-link" aria-expanded={all} onClick={() => setAll(!all)}>
              {all ? 'Show the largest 5' : `Everything else (${rest.length} ${rest.length === 1 ? 'category' : 'categories'})`}
              {' '}<PIcon name={all ? 'chevronDown' : 'chevronRight'} size={14} />
            </button>
          )}
        </section>
      )}
      {children}
    </div>
  );
}

/** B-02: change one budget as a share of usual, the dollars beside it. */
export function ChangeBudget({ row, onClose, onSave }) {
  const [pct, setPct] = useState(row.pct);
  const [custom, setCustom] = useState(!PRESETS.includes(row.pct));
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const save = () => {
    setSaving(true);
    setError(null);
    onSave(pct).catch((err) => setError(err.message)).finally(() => setSaving(false));
  };
  return (
    <DetailPanel label="Change this budget" overline={row.category} onClose={onClose}>
      <div className="hm-form bd-change-panel">
        <h1 className="pk-h2">Change this budget</h1>
        <p className="pk-muted">{`Your usual month: ${shown(row.usual)}`}</p>
        {custom ? (
          <div className="gl-field">
            <label htmlFor="bd-custom">{`Custom: ${pct}% of usual`}</label>
            <input id="bd-custom" type="range" min={CUSTOM.min} max={CUSTOM.max} step={CUSTOM.step}
                   value={pct} onChange={(e) => setPct(Number(e.target.value))} />
          </div>
        ) : (
          <Segmented label="Share of your usual month" value={pct}
                     options={PRESETS.map((p) => ({ value: p, label: `${p}%` }))} onChange={setPct} />
        )}
        <p className="pk-amount bd-amount">{`${shown(budgetFor(row.usual, pct))} a month`}</p>
        <p className="pk-muted">{changeWords(row.usual, pct)}</p>
        <button type="button" className="hm-link" onClick={() => {
          if (custom && !PRESETS.includes(pct)) setPct(100);
          setCustom(!custom);
        }}>
          {custom ? 'Use a preset' : 'Use a custom %'} <PIcon name="chevronRight" size={14} />
        </button>
        {error && <p className="txd-hint" role="alert"><PIcon name="alert" size={14} /> {error}</p>}
        <PButton onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</PButton>
      </div>
    </DetailPanel>
  );
}
