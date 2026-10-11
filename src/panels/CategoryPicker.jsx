import { useEffect, useMemo, useState } from 'react';
import { ChipOption, Choice, ImpactNote, PButton } from '../pearl/kit.jsx';
import { previewCategory } from '../api.js';

/**
 * Change category (Pearl R-02, THL-123): every category as a chip, in the five
 * groups the list filters by, with what the choice would do said underneath
 * before it is saved, and "Apply to all from <merchant>".
 *
 * The impact line comes from the server, worked out on the real ledger, so it
 * says exactly what Allowance will show afterwards.
 */

// The groups in the Handoff file's order, and how many chips each shows
// before "More…".
const GROUPS = [
  { key: 'essentials', title: 'Essentials', shown: 8,
    order: ['Groceries', 'Rent & Housing', 'Utilities', 'Phone & Internet', 'Insurance',
      'Transport', 'Gas & Fuel', 'Health'] },
  { key: 'lifestyle', title: 'Lifestyle', shown: 11,
    order: ['Dining', 'Food Delivery', 'Coffee', 'Alcohol & Bars', 'Shopping', 'Personal Care',
      'Fitness', 'Entertainment', 'Streaming', 'Travel', 'Gifts & Charity'] },
  { key: 'savings', title: 'Savings', order: ['Saved'] },
  { key: 'income', title: 'Income', order: ['Income'] },
  { key: 'transfer', title: 'Not spending', order: ['Transfers', 'Lent'] },
];

// Names that read better as an answer than as a ledger heading.
export const CATEGORY_LABEL = { Transfers: 'Between my accounts' };
export const categoryLabel = (name) => CATEGORY_LABEL[name] ?? name;

/** The categories laid out by group, as R-02 shows them. */
export function groupCategories(categories, { only } = {}) {
  const names = categories
    .filter((c) => c.name !== 'Unsorted transfers' && (!only || only(c)));
  return GROUPS.map((g) => {
    const mine = names.filter((c) => c.group === g.key).map((c) => c.name);
    const ordered = [
      ...g.order.filter((n) => mine.includes(n)),
      ...mine.filter((n) => !g.order.includes(n)),
    ];
    return { ...g, names: ordered };
  }).filter((g) => g.names.length > 0);
}

export function CategoryChips({ groups, value, suggested, onChange, label = 'Category' }) {
  const [open, setOpen] = useState({});
  return (
    <div className="pk-opt-groups" role="radiogroup" aria-label={label}>
      {groups.map((g) => {
        const cut = g.shown ?? g.names.length;
        const hidden = g.names.slice(cut);
        const all = open[g.key] || hidden.includes(value) || hidden.includes(suggested);
        const names = all ? g.names : g.names.slice(0, cut);
        return (
          <div className="pk-opt-group" key={g.key}>
            <p className="pk-overline">{g.title}</p>
            <div className="pk-opts">
              {names.map((n) => (
                <ChipOption key={n} label={categoryLabel(n)} selected={value === n}
                            suggested={suggested === n} onSelect={() => onChange(n)} />
              ))}
              {!all && hidden.length > 0 && (
                <ChipOption link label="More…" onSelect={() => setOpen({ ...open, [g.key]: true })} />
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Chips, the impact line, Apply to all, and Save. */
export default function CategoryPicker({ tx, categories, busy, onSave, saveLabel = 'Save',
                                         allowApplyAll = true, only }) {
  const current = tx.category;
  const unsorted = current === 'Unsorted transfers';
  const [pick, setPick] = useState(unsorted ? '' : current);
  const [always, setAlways] = useState(false);
  const [impact, setImpact] = useState(null);
  const [count, setCount] = useState(null);
  const groups = useMemo(() => groupCategories(categories, { only }), [categories, only]);
  const applyAll = allowApplyAll && !unsorted;

  // How many rows "Apply to all" would re-file, once.
  useEffect(() => {
    if (!applyAll) return undefined;
    let live = true;
    previewCategory(tx.id, current, false)
      .then((r) => { if (live) setCount(r.merchant_count); }).catch(() => {});
    return () => { live = false; };
  }, [tx.id, current, applyAll]);

  // What the choice would do, said before it is made.
  useEffect(() => {
    if (!pick || (pick === current && !always)) { setImpact(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      previewCategory(tx.id, pick, always)
        .then((r) => { if (live) setImpact(r); }).catch(() => { if (live) setImpact(null); });
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [tx.id, pick, always, current]);

  const changed = !!pick && (pick !== current || always);
  return (
    <div className="txd-step">
      <CategoryChips groups={groups} value={pick} onChange={setPick}
                     suggested={tx.suggested && !unsorted ? current : null} />
      <ImpactNote>{impact?.line}</ImpactNote>
      {applyAll && (
        <Choice type="checkbox" checked={always} onChange={setAlways}
                label={`Apply to all from ${tx.merchant}`}
                description={!(count > 1) ? 'This one, and new ones from now on.'
                  : `${count - 1} past transaction${count === 2 ? '' : 's'}, and new ones from now on.`} />
      )}
      <PButton className="txd-save" disabled={busy || !changed}
               onClick={() => onSave(pick, applyAll && always)}>
        {saveLabel}
      </PButton>
    </div>
  );
}
