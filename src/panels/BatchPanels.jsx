import { useEffect, useMemo, useState } from 'react';
import { Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { CategoryChips, groupCategories } from './CategoryPicker.jsx';
import { TagEditor } from './WhatWasThis.jsx';
import { batchMark, batchTags, getTags } from '../api.js';

/**
 * A selection, answered at once (2026-10-14): "Mark as…" with the cases
 * that need nothing per row, and "Tag" with her tags. Both answer like a
 * batch change of category: one toast, one Undo, never a merchant rule.
 */

export const BATCH_CASES = [
  { key: 'spending', label: 'A purchase', needs: 'category', effect: 'Counts as spending, in the category you pick.' },
  { key: 'moved', label: 'Moved between my accounts', effect: 'Nothing changes in your numbers.' },
  { key: 'saved', label: 'Put into savings or investments', effect: 'Adds to what you put away. Not spending.' },
  { key: 'lent', label: 'Lent to someone', effect: 'Not spending: it comes back later.' },
  { key: 'work', label: 'Work expenses I’ll be reimbursed for', effect: 'Left out until the reimbursement arrives.' },
  { key: 'not_mine', label: 'Not mine', needs: 'reason', effect: 'Left out of everything.' },
];

export function BatchMarkPanel({ ids, categories = [], onDone, onClose }) {
  const [key, setKey] = useState('');
  const [category, setCategory] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const groups = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden,
  }), [categories]);
  const current = BATCH_CASES.find((c) => c.key === key);
  const ok = current && (current.needs !== 'category' || !!category);
  const n = ids.length;
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { case: key };
      if (current.needs === 'category') body.category = category;
      if (current.needs === 'reason') body.reason = reason;
      onDone(await batchMark(ids, body));
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };
  return (
    <DetailPanel label={`Mark ${n} transaction${n === 1 ? '' : 's'} as`} overline="Selection"
                 onClose={onClose}>
      <h2 className="pk-h2">What were these?</h2>
      <p className="pk-muted">The same answer for all {n}. Nothing becomes a rule.</p>
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      <div className="pk-choices" role="radiogroup" aria-label="What were these?">
        {BATCH_CASES.map((c) => (
          <div key={c.key} className={`wwt-case${key === c.key ? ' on' : ''}`}>
            <Choice name="batch-case" checked={key === c.key} onChange={() => setKey(c.key)}
                    label={c.label} description={c.effect} />
            {key === c.key && c.needs === 'category' && (
              <div className="wwt-sub">
                <CategoryChips groups={groups} value={category} onChange={setCategory}
                               label="What were they for?" />
              </div>
            )}
            {key === c.key && c.needs === 'reason' && (
              <div className="wwt-sub">
                <input className="wwt-input" type="text" maxLength={80} placeholder="Why? (optional)"
                       aria-label="Why?" value={reason} onChange={(e) => setReason(e.target.value)} />
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="txd-actions">
        <PButton disabled={busy || !ok} onClick={save}>{busy ? 'Saving…' : `Mark ${n}`}</PButton>
      </div>
    </DetailPanel>
  );
}

export function BatchTagPanel({ ids, onDone, onClose }) {
  const [tags, setTags] = useState([]);
  const [known, setKnown] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    let live = true;
    getTags().then((d) => { if (live) setKnown((d.tags ?? []).map((t) => t.tag)); }).catch(() => {});
    return () => { live = false; };
  }, []);
  const n = ids.length;
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await batchTags(ids, tags, []));
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };
  return (
    <DetailPanel label={`Tag ${n} transaction${n === 1 ? '' : 's'}`} overline="Selection" onClose={onClose}>
      <h2 className="pk-h2">Tag these</h2>
      <p className="pk-muted">A tag groups transactions without changing their category: a trip,
        a renovation, a wedding. Filter by it to see the total.</p>
      {error && <p className="txd-error" role="alert">{error.message}</p>}
      <TagEditor tags={tags} known={known} onChange={setTags} />
      <div className="txd-actions">
        <PButton disabled={busy || !tags.length} onClick={save}>{busy ? 'Saving…' : `Tag ${n}`}</PButton>
      </div>
    </DetailPanel>
  );
}
