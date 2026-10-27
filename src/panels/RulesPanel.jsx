import { useCallback, useEffect, useMemo, useState } from 'react';
import { TAGS_ON } from '../features.js';
import { ErrorNote } from '../components/ui.jsx';
import {
  deleteRule, editRule, getRules, money, renameTag, setCategoryHidden, setCategoryKind, setMerchantName,
} from '../api.js';
import { Alert, DetailPanel, FilterChip, PButton, Segmented, Toast } from '../pearl/kit.jsx';
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

/** CR-02: her names for merchants — the bank's spelling, and hers. */
export function NamesSection({ names = [], onRename, onForget }) {
  return (
    <section className="pf-section" aria-label="Merchants">
      <p className="pk-muted">Give a merchant a name you’ll recognise. It shows everywhere and in search.</p>
      {names.length === 0 ? (
        <p className="pk-muted">No merchants renamed yet. Open a transaction and choose Rename merchant.</p>
      ) : (
        <ul className="pf-list">
          {names.map((n) => (
            <li className="pf-row static" key={n.key}>
              <div className="pf-row-main">
                <span className="pf-row-text">
                  <span className="pf-row-name">{n.name}</span>
                  <span className="pf-row-sub">{`From your bank: ${n.merchant}`}</span>
                </span>
              </div>
              <span className="pf-row-links">
                <button type="button" className="pf-text-link" onClick={() => onRename(n)}>Rename</button>
                <button type="button" className="pf-text-link" onClick={() => onForget(n)}>Use the bank’s name</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** CR-03: her tags, how many rows wear each and what they come to. */
export function TagsSection({ tags = [], onRename, onRemove }) {
  return (
    <section className="pf-section" aria-label="Tags">
      <p className="pk-muted">Tags group transactions across categories and months. They never change your totals.</p>
      {tags.length === 0 ? (
        <p className="pk-muted">No tags yet. Tag a transaction, or several at once, from Cash flow.</p>
      ) : (
        <ul className="pf-list">
          {tags.map((t) => (
            <li className="pf-row static" key={t.tag}>
              <div className="pf-row-main">
                <span className="pf-row-text">
                  <span className="pf-row-name">{t.tag}</span>
                  <span className="pf-row-sub">
                    {`${t.count} transaction${t.count === 1 ? '' : 's'} · ${money(t.spent, { cents: true })}`}
                  </span>
                </span>
              </div>
              <span className="pf-row-links">
                <button type="button" className="pf-text-link" onClick={() => onRename(t)}>Rename</button>
                <button type="button" className="pf-text-link" onClick={() => onRemove(t)}>Remove</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const GROUP_NAMES = { essentials: 'Essentials', lifestyle: 'Lifestyle' };

/** CR-01: every spending category — Pearl decides · Fixed, Always Fixed,
 * Always Variable — and Hide / Show. */
export function CategoriesSection({ categories = [], kinds = {}, pearl = {}, hidden = [], onKind,
                                    onHide }) {
  const spending = categories.filter((c) => !['income', 'savings', 'transfer'].includes(c.group)
    && c.name !== 'Unsorted transfers' && c.name !== 'Other');
  return (
    <section className="pf-section" aria-label="Categories">
      <p className="pk-muted">
        Pearl decides whether a category is Fixed (bills that come regularly) or Variable. Change
        any of them. Hidden categories don’t show in pickers.
      </p>
      <ul className="pf-list">
        {spending.map((c) => {
          const off = hidden.includes(c.name);
          const decided = pearl[c.name] === 'fixed' ? 'Fixed' : 'Variable';
          const choices = [{ value: '', label: `Pearl decides · ${decided}` },
                           { value: 'fixed', label: 'Always Fixed' },
                           { value: 'variable', label: 'Always Variable' }];
          return (
            <li className="pf-row static" key={c.name}>
              <div className="pf-row-main">
                <span className="pf-row-text">
                  <span className="pf-row-name">{c.name}</span>
                  <span className="pf-row-sub">{GROUP_NAMES[c.group] ?? c.group}</span>
                </span>
              </div>
              <span className="pf-row-links">
                {off ? <span className="pk-filter" aria-label={`${c.name} is hidden`}>Hidden</span> : (
                  <FilterChip label={`${c.name}: fixed or variable`} value={kinds[c.name] ?? ''}
                              options={choices} active={!!kinds[c.name]}
                              onChange={(v) => onKind(c.name, v || null)} />
                )}
                <button type="button" className="pf-text-link" onClick={() => onHide(c.name, !off)}>
                  {off ? 'Show' : 'Hide'}
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const TABS = [{ value: 'rules', label: 'Rules' }, { value: 'categories', label: 'Categories' },
              { value: 'merchants', label: 'Merchants' },
              ...(TAGS_ON ? [{ value: 'tags', label: 'Tags' }] : [])];

export function RulesPage({ rules, onTab, onEdit, categories = [], kinds = {}, pearlKinds = {},
                            onKind, names = [], tags = [], hidden = [], onRenameName, onForgetName,
                            onRenameTag, onRemoveTag, onHide, tab = 'rules', onTabChange }) {
  if (!TAGS_ON && tab === 'tags') tab = 'rules';   // tags are off for now (2026-10-26)
  return (
    <div className="pk hm-page pf-page">
      <PageHead trail={[{ label: 'Profile', to: 'profile' }, { label: 'Categories and rules' }]}
                title="Categories and rules" onTab={onTab} />
      <div className="pf-tabs">
        <Segmented label="Categories and rules" value={tab} options={TABS} onChange={onTabChange} />
      </div>
      {tab === 'rules' && (
        <>
          <p className="pf-intro">
            When you sort something and tick “Remember”, Pearl sorts the next ones the same way.
            Your rules always win over ours.
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
        </>
      )}
      {tab === 'categories' && onKind && (
        <CategoriesSection categories={categories} kinds={kinds} pearl={pearlKinds} hidden={hidden}
                           onKind={onKind} onHide={onHide} />
      )}
      {tab === 'merchants' && <NamesSection names={names} onRename={onRenameName} onForget={onForgetName} />}
      {TAGS_ON && tab === 'tags' && <TagsSection tags={tags} onRename={onRenameTag} onRemove={onRemoveTag} />}
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
  const [tab, setTab] = useState('rules');
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
                 kinds={data.kinds ?? {}} pearlKinds={data.pearl_kinds ?? {}} names={data.names ?? []}
                 tags={data.tags ?? []} hidden={data.hidden ?? []} tab={tab} onTabChange={setTab}
                 onRenameName={async (n) => {
                   const name = window.prompt(`Call ${n.merchant}:`, n.name);
                   if (!name || name.trim() === n.name) return;
                   await setMerchantName(n.merchant, name.trim());
                   await done(`${n.merchant} is ${name.trim()} now.`);
                 }}
                 onKind={async (category, kind) => {
                   await setCategoryKind(category, kind);
                   await done(kind ? `${category} is always ${kind === 'fixed' ? 'Fixed' : 'Variable'} now.`
                     : `Pearl decides ${category} again.`);
                 }}
                 onForgetName={async (n) => {
                   await deleteRule(`name:${n.key}`);
                   await done(`${n.merchant} uses the bank’s name again.`);
                 }}
                 onRenameTag={async (t) => {
                   const name = window.prompt(`Rename “${t.tag}” to:`, t.tag);
                   if (!name || name.trim() === t.tag) return;
                   await renameTag(t.tag, name.trim());
                   await done(`${t.tag} is ${name.trim()} now.`);
                 }}
                 onRemoveTag={async (t) => {
                   if (!window.confirm(`Take “${t.tag}” off ${t.count} transaction${t.count === 1 ? '' : 's'}?`)) return;
                   await renameTag(t.tag, null);
                   await done(`${t.tag} removed.`);
                 }}
                 onHide={async (category, hide) => {
                   await setCategoryHidden(category, hide);
                   await done(hide ? `${category} is out of the pickers.` : `${category} is back.`);
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
