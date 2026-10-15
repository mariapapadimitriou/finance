import { useEffect, useMemo, useState } from 'react';
import { DetailPanel, PButton, ChipOption, txAmount } from '../pearl/kit.jsx';
import { addRange, changeRange, getRanges, previewRange, removeRange } from '../api.js';

/**
 * Sort a date range (DR-01) and Sorted together (DR-02), THL-231.
 *
 * A range gives every purchase between two dates one category, like a
 * trip; the summary says what moves and what stays before it's done, and
 * Sorted together lists each range with its running total, to change or
 * remove (finance/ranges.py).
 */

const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "Sep 19–23", "Aug 28 – Sep 2". */
export function rangeWords(first, last) {
  const [fm, fd] = [Number(first.slice(5, 7)), Number(first.slice(8, 10))];
  const [lm, ld] = [Number(last.slice(5, 7)), Number(last.slice(8, 10))];
  if (first === last) return `${SHORT[fm - 1]} ${fd}`;
  if (fm === lm && first.slice(0, 4) === last.slice(0, 4)) return `${SHORT[fm - 1]} ${fd}–${ld}`;
  return `${SHORT[fm - 1]} ${fd} – ${SHORT[lm - 1]} ${ld}`;
}

// The categories a trip usually is, first; the rest behind More….
const FIRST = ['Travel', 'Dining', 'Gifts & Charity'];

export function SortRangePanel({ categories = [], range = null, onDone, onClose }) {
  const [name, setName] = useState(range?.name || '');
  const [first, setFirst] = useState(range?.first || '');
  const [last, setLast] = useState(range?.last || '');
  const [category, setCategory] = useState(range?.category || 'Travel');
  const [more, setMore] = useState(false);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const names = useMemo(() => categories
    .filter((c) => ['essentials', 'lifestyle'].includes(c.group) && !c.hidden).map((c) => c.name),
  [categories]);
  const shown = more ? names : [...FIRST.filter((n) => names.includes(n)),
    ...(names.includes(category) && !FIRST.includes(category) ? [category] : [])];
  const complete = !!first && !!last && !!category && last >= first;

  useEffect(() => {
    if (!complete) { setPreview(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      previewRange({ name, first, last, category, id: range?.id })
        .then((p) => { if (live) { setPreview(p); setError(null); } })
        .catch((e) => { if (live) { setPreview(null); setError(e.message); } });
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [first, last, category, complete]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { name, first, last, category };
      onDone(range ? await changeRange(range.id, body) : await addRange(body));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  const n = preview?.count ?? 0;
  return (
    <DetailPanel label="Sort a date range" overline="Sort a date range" onClose={onClose}>
      <h2 className="pk-h2">{range ? 'Change this range' : 'Sort a date range'}</h2>
      <p className="pk-muted">Give every purchase between two dates one category, like a trip.
        You can undo it any time.</p>
      <div className="txd-field">
        <label className="pk-label" htmlFor="rg-name">Name</label>
        <input id="rg-name" type="text" maxLength={60} placeholder="Montréal trip" value={name}
               autoComplete="off" onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="rg-dates">
        <div className="txd-field">
          <label className="pk-label" htmlFor="rg-first">First day</label>
          <input id="rg-first" type="date" value={first} onChange={(e) => setFirst(e.target.value)} />
        </div>
        <div className="txd-field">
          <label className="pk-label" htmlFor="rg-last">Last day</label>
          <input id="rg-last" type="date" value={last} min={first || undefined}
                 onChange={(e) => setLast(e.target.value)} />
        </div>
      </div>
      <div className="txd-field">
        <p className="pk-label">Category</p>
        <div className="pk-opts" role="radiogroup" aria-label="Category">
          {shown.map((c) => (
            <ChipOption key={c} label={c} selected={category === c} onSelect={() => setCategory(c)} />
          ))}
          {!more && names.length > shown.length && (
            <ChipOption link label="More…" onSelect={() => setMore(true)} />
          )}
        </div>
      </div>
      {preview && (
        <div className="wwt-effect rg-summary" role="status" aria-live="polite">
          <p className="pk-label">{preview.title}</p>
          {preview.mostly && <p>{preview.mostly}</p>}
          <p className="pk-muted">{preview.staying}</p>
        </div>
      )}
      {error && <p className="txd-error" role="alert">{error}</p>}
      <div className="txd-actions">
        <PButton disabled={busy || !complete || !preview || n === 0} onClick={save}>
          {busy ? 'Sorting…' : range ? `Re-sort ${n} purchase${n === 1 ? '' : 's'}`
            : `Sort ${n} purchase${n === 1 ? '' : 's'}`}
        </PButton>
        <PButton variant="secondary" onClick={onClose}>Cancel</PButton>
      </div>
    </DetailPanel>
  );
}

export function SortedTogetherPanel({ onChange, onAnother, onRemoved, onClose }) {
  const [ranges, setRanges] = useState(null);
  const [error, setError] = useState(null);
  const load = () => getRanges().then((d) => setRanges(d.ranges)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const remove = async (r) => {
    try {
      const res = await removeRange(r.id);
      onRemoved?.(res);
      load();
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <DetailPanel label="Sorted together" overline="Sorted together" onClose={onClose}>
      <h2 className="pk-h2">Sorted together</h2>
      <p className="pk-muted">Each date range you sorted, with its running total. Change one to
        re-apply it; remove one to put every row back.</p>
      {error && <p className="txd-error" role="alert">{error}</p>}
      {ranges === null ? <p className="pk-muted">Loading…</p> : ranges.length === 0 ? (
        <p className="pk-muted">Nothing sorted together yet.</p>
      ) : (
        <div className="rg-list">
          {ranges.map((r) => (
            <section key={r.id} className="rg-card" aria-label={r.name}>
              <div className="rg-card-top">
                <span>{r.name}</span>
                <span className="rg-total">{txAmount(r.total)}</span>
              </div>
              <p className="pk-label pk-muted">
                {`${rangeWords(r.first, r.last)} · ${r.category} · ${r.count} purchase${r.count === 1 ? '' : 's'}`}
              </p>
              <div className="rg-card-actions">
                <PButton variant="text" onClick={() => onChange(r)}>Change</PButton>
                <PButton variant="text" onClick={() => remove(r)}>Remove</PButton>
              </div>
            </section>
          ))}
        </div>
      )}
      <div className="txd-actions">
        <PButton onClick={onAnother}>Sort another range</PButton>
        <PButton variant="secondary" onClick={onClose}>Close</PButton>
      </div>
    </DetailPanel>
  );
}
