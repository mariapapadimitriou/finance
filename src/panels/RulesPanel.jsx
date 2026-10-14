import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { deleteRule, editRule, getRules, setCategoryKind } from '../api.js';
import { Alert, DetailPanel, PButton, Toast, FilterChip } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CategoryChips, categoryLabel, groupCategories } from './CategoryPicker.jsx';
import { PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Categories and rules (Pearl S-03).
 *
 * Every rule she saved: "Apply to all from Loblaws" in Change category and
 * "Remember where these go" in Needs a look (by merchant, and by where a
 * transfer went), and the "leave out every transaction like this" rules,
 * which moved here from the temporary Exclusions card on Accounts.
 *
 * Edit opens the category chips (CategoryPicker's) to change what a sorting
 * rule files things under, or delete it. Deleting a sorting rule doesn't
 * change what it already sorted; removing a leave-out rule puts what it left
 * out back, and the panel says so before it's done.
 */

/** "Always Groceries", "Always left out". */
export function ruleWords(r) {
  if (r.kind === 'exclusion') return 'Always left out';
  return `Always ${categoryLabel(r.category)}`;
}

const KIND_CHOICES = [{ value: '', label: 'Pearl decides' }, { value: 'fixed', label: 'Always Fixed' },
                      { value: 'variable', label: 'Always Variable' }];

/** Fixed or Variable, category by category (finance/kinds.py). */
export function KindsSection({ categories = [], kinds = {}, onKind }) {
  const spending = categories.filter((c) => !['income', 'savings', 'transfer'].includes(c.group)
    && c.name !== 'Unsorted transfers');
  if (!spending.length) return null;
  return (
    <section className="hm-card pf-kinds" aria-labelledby="pf-kinds-title">
      <h2 className="pk-h3" id="pf-kinds-title">Fixed or variable</h2>
      <p className="pk-muted">
        Pearl counts the bills it sees recurring as Fixed and everything else as Variable. Say
        otherwise for any category.
      </p>
      <ul className="pf-kind-list">
        {spending.map((c) => (
          <li key={c.name}>
            <span className="pf-row-name">{c.name}</span>
            <FilterChip label={`${c.name}: fixed or variable`} value={kinds[c.name] ?? ''}
                        options={KIND_CHOICES} active={!!kinds[c.name]}
                        onChange={(v) => onKind(c.name, v || null)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RulesPage({ rules, onTab, onEdit, categories = [], kinds = {}, onKind }) {
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={[{ label: 'Profile', to: 'profile' }, { label: 'Categories and rules' }]}
                title="Categories and rules" onTab={onTab} />
      <p className="pf-intro">
        When you sort something and tick “Remember”, Pearl sorts the next ones the same way. Your
        rules always win over ours.
      </p>
      {rules.length === 0 ? (
        <section className="hm-card">
          <h2 className="pk-h3">No saved rules yet</h2>
          <p className="pk-muted">
            Change a transaction’s category and tick “Apply to all”, and the rule shows up here.
          </p>
        </section>
      ) : (
        <ul className="pf-list">
          {rules.map((r) => (
            <li className="pf-row static" key={r.id}>
              <div className="pf-row-main">
                <span className="pf-row-text">
                  <span className="pf-row-name">{r.name}</span>
                  <span className="pf-row-sub">{ruleWords(r)}</span>
                </span>
              </div>
              <button type="button" className="pf-row-link" onClick={() => onEdit(r)}
                      aria-label={`Edit the rule for ${r.name}`}>
                Edit <PIcon name="chevronRight" size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="pf-foot">Deleting a rule doesn’t change transactions you’ve already sorted.</p>
      {onKind && <KindsSection categories={categories} kinds={kinds} onKind={onKind} />}
    </div>
  );
}

/** Change what a rule files things under, or delete it. */
export function RulePanel({ rule, categories, onClose, onSave, onDelete }) {
  const [pick, setPick] = useState(rule.category);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const groups = useMemo(() => groupCategories(categories), [categories]);
  const run = (fn) => {
    setBusy(true);
    setError(null);
    fn().catch((e) => { setError(e.message); setBusy(false); });
  };
  const leaveOut = rule.kind === 'exclusion';
  return (
    <DetailPanel label={`Rule for ${rule.name}`} overline="Rule" onClose={onClose}>
      <h1 className="pk-h2">{rule.name}</h1>
      {leaveOut ? (
        <>
          <p className="pk-muted">
            {`Always left out${rule.reason ? `: ${rule.reason}` : ''}. ${rule.matched === 1
              ? 'It leaves out 1 transaction now.'
              : rule.matched > 1 ? `It leaves out ${rule.matched} transactions now.`
                : 'It catches new ones as they come in.'}`}
          </p>
          <p className="pk-muted">
            Removing it puts what it left out back into your spending.
          </p>
        </>
      ) : (
        <>
          <p className="pk-muted">
            {`Pearl files every transaction from ${rule.name} as ${categoryLabel(rule.category)}. Change it and those transactions move too.`}
          </p>
          <CategoryChips groups={groups} value={pick} onChange={setPick} />
        </>
      )}
      {error && <Alert tone="caution">{error}</Alert>}
      {leaveOut ? (
        <PButton disabled={busy} onClick={() => run(onDelete)}>Remove this rule</PButton>
      ) : (
        <>
          <PButton disabled={busy || pick === rule.category} onClick={() => run(() => onSave(pick))}>
            Save
          </PButton>
          <PButton variant="text" disabled={busy} onClick={() => run(onDelete)}>Delete this rule</PButton>
        </>
      )}
    </DetailPanel>
  );
}

export default function RulesPanel({ categories = [], onTab, onChanged, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [note, setNote] = useState(null);
  const load = useCallback(() => getRules().then(setData).catch(setError), []);
  useEffect(() => { load(); }, [load, version]);

  if (error && !data) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading your rules…</p></div>;
  const done = async (text) => {
    setEditing(null);
    setNote(text);
    await load();
    await onChanged?.();
  };
  return (
    <>
      <RulesPage rules={data.rules} onTab={onTab} onEdit={setEditing} categories={categories}
                 kinds={data.kinds ?? {}}
                 onKind={async (category, kind) => {
                   await setCategoryKind(category, kind);
                   await done(kind ? `${category} is always ${kind === 'fixed' ? 'Fixed' : 'Variable'} now.`
                     : `Pearl decides ${category} again.`);
                 }} />
      {editing && (
        <div className="pk">
          <RulePanel rule={editing} categories={categories} onClose={() => setEditing(null)}
                     onSave={async (category) => {
                       await editRule(editing.id, category);
                       await done(`${editing.name} is always ${categoryLabel(category)} now.`);
                     }}
                     onDelete={async () => {
                       await deleteRule(editing.id);
                       await done('Rule deleted.');
                     }} />
        </div>
      )}
      {note && <div className="pk"><Toast onDone={() => setNote(null)}>{note}</Toast></div>}
    </>
  );
}
