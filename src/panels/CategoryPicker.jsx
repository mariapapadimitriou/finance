import { useEffect, useMemo, useState } from 'react';
import { Choice, ImpactNote, PButton } from '../pearl/kit.jsx';
import PIcon, { categoryIcon } from '../pearl/icons.jsx';
import { previewCategory } from '../api.js';

/**
 * Change category (Pearl R-02, THL-123): every category as a chip, in the five
 * groups the list filters by, with what the choice would do said underneath
 * before it is saved, and "Apply to all from <merchant>".
 *
 * The impact line comes from the server, worked out on the real ledger, so it
 * says exactly what Allowance will show afterwards.
 */

// The groups in the Handoff file's order. Every category shows, every
// time, in the same place (2026-10-21): the tiles are a grid she learns, not
// a cloud of chips behind "More…". The order within a group puts the ones
// she reaches for most first, then the rest alphabetically.
const GROUPS = [
  { key: 'essentials', title: 'Essentials',
    order: ['Groceries', 'Rent & Housing', 'Utilities', 'Phone & Internet', 'Insurance',
      'Transport', 'Gas & Fuel', 'Health'] },
  { key: 'lifestyle', title: 'Lifestyle',
    order: ['Dining', 'Food Delivery', 'Coffee', 'Alcohol & Bars', 'Shopping', 'Personal Care',
      'Fitness', 'Entertainment', 'Streaming', 'Travel', 'Gifts & Charity'] },
  { key: 'savings', title: 'Savings', order: ['Saved'] },
  { key: 'income', title: 'Income', order: ['Income'] },
  { key: 'transfer', title: 'Not spending', order: ['Transfers', 'Lent', 'Borrowed'] },
];

// Names that read better as an answer than as a ledger heading. Transfers
// is just Transfers (2026-10-14), no longer "Between my accounts".
export const CATEGORY_LABEL = {};
export const categoryLabel = (name) => CATEGORY_LABEL[name] ?? name;

/** The categories laid out by group, as R-02 shows them. */
export function groupCategories(categories, { only, keep } = {}) {
  // A category she hid (Profile › Categories and rules) stays out of the
  // chips, except the one a row is already in.
  const names = categories
    .filter((c) => c.name !== 'Unsorted transfers' && (!c.hidden || c.name === keep)
      && (!only || only(c)));
  return GROUPS.map((g) => {
    const mine = names.filter((c) => c.group === g.key).map((c) => c.name);
    const ordered = [
      ...g.order.filter((n) => mine.includes(n)),
      ...mine.filter((n) => !g.order.includes(n)).sort((a, b) => a.localeCompare(b)),
    ];
    return { ...g, names: ordered };
  }).filter((g) => g.names.length > 0);
}

/** One category as a tile: its icon in rose on a blush disc, and its name. */
export function CategoryTile({ name, selected = false, suggested = false, onSelect, disabled = false }) {
  return (
    <button type="button" role="radio" aria-checked={selected} disabled={disabled}
            className={`pk-tile${selected ? ' on' : ''}${suggested && !selected ? ' guess' : ''}`}
            onClick={onSelect}>
      <span className="pk-tile-icon" aria-hidden="true"><PIcon name={categoryIcon(name)} size={20} /></span>
      <span className="pk-tile-label">{categoryLabel(name)}</span>
      {selected && <span className="pk-tile-check" aria-hidden="true"><PIcon name="check" size={12} /></span>}
    </button>
  );
}

/**
 * The categories as a grid of tiles (2026-10-21), grouped, every one shown in
 * the same place every time, with a search box above for the days she knows
 * the word. Kept under its old name: every picker in the app renders this.
 */
export function CategoryChips({ groups, value, suggested, onChange, label = 'Category', search = true }) {
  const [q, setQ] = useState('');
  const needle = q.trim().toLowerCase();
  const total = groups.reduce((n, g) => n + g.names.length, 0);
  const shown = needle
    ? groups.map((g) => ({ ...g, names: g.names.filter((n) => categoryLabel(n).toLowerCase().includes(needle)) }))
      .filter((g) => g.names.length)
    : groups;
  return (
    <div className="pk-tile-picker">
      {search && total > 8 && (
        <div className="pk-tile-search">
          <PIcon name="search" size={16} />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a category"
                 aria-label="Find a category" autoComplete="off"
                 onKeyDown={(e) => {
                   // Enter picks the one match, so a typed name is one keystroke away.
                   if (e.key !== 'Enter') return;
                   const hits = shown.flatMap((g) => g.names);
                   if (hits.length === 1) { e.preventDefault(); onChange(hits[0]); }
                 }} />
        </div>
      )}
      <div className="pk-tile-groups" role="radiogroup" aria-label={label}>
        {shown.map((g) => (
          <div className="pk-tile-group" key={g.key}>
            <p className="pk-overline">{g.title}</p>
            <div className="pk-tile-grid">
              {g.names.map((n) => (
                <CategoryTile key={n} name={n} selected={value === n} suggested={suggested === n}
                              onSelect={() => onChange(n)} />
              ))}
            </div>
          </div>
        ))}
        {needle && !shown.length && <p className="pk-muted">Nothing called “{q.trim()}”.</p>}
      </div>
    </div>
  );
}

/** Chips, the impact line, Apply to all, and Save. */
export default function CategoryPicker({ tx, categories, busy, onSave, saveLabel = 'Save',
                                         allowApplyAll = true, only, confirmable = false,
                                         label = 'Category' }) {
  const current = tx.category;
  const unsorted = current === 'Unsorted transfers';
  const [pick, setPick] = useState(unsorted ? '' : current);
  const [always, setAlways] = useState(false);
  const [impact, setImpact] = useState(null);
  const [count, setCount] = useState(null);
  const groups = useMemo(() => groupCategories(categories, { only, keep: current }),
                         [categories, only, current]);
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

  // In Needs a look, saving Pearl's own guess unchanged confirms it.
  const changed = !!pick && (pick !== current || always || confirmable);
  return (
    <div className="txd-step">
      <CategoryChips groups={groups} value={pick} onChange={setPick} label={label}
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
