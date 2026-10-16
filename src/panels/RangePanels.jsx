import { useEffect, useMemo, useState } from 'react';
import { Choice, ChipOption, DetailPanel, PButton, txAmount } from '../pearl/kit.jsx';
import { money } from '../api.js';
import { addRange, changeRange, previewRange } from '../api.js';

/**
 * Sort these days (CAL-07, CAL-08; THL-220, 2026-10-16), and Days sorted
 * together (CAL-09), under the calendar.
 *
 * A range gives every purchase between two dates one category, like a
 * trip, with an optional name — and, only if she wants, a treasure chest
 * that paid for them, so they leave the month's spending and come out of
 * the chest instead. The summary says what moves, what stays and what a
 * chest would do before it's done (finance/ranges.py). The dates come from
 * the calendar (Select days); changing a range from the list can move them.
 */

const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
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

/** "Oct 4–7 · Travel · 23 purchases · paid from Japan trip" */
export function rangeLine(r) {
  const n = r.count;
  return `${rangeWords(r.first, r.last)} · ${r.category} · ${n} purchase${n === 1 ? '' : 's'}`
    + (r.bank ? ` · paid from ${r.bank}` : '');
}

/**
 * The sheet. `dates` ({first, last, label?, words?}) comes from Select
 * days and is fixed; `range` is one from the list, to change, with its
 * dates editable; `banks` are her treasure chests.
 */
export function SortRangePanel({ categories = [], banks = [], dates = null, range = null,
                                 onDone, onClose }) {
  const [name, setName] = useState(range?.name || '');
  const [first, setFirst] = useState(range?.first || dates?.first || '');
  const [last, setLast] = useState(range?.last || dates?.last || '');
  const [category, setCategory] = useState(range?.category || 'Travel');
  const [bankId, setBankId] = useState(range?.bank_id ? String(range.bank_id) : '');
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
  const fixed = !!dates && !range;
  const month = first ? MONTHS[Number(first.slice(5, 7)) - 1] : 'the month';
  const bank = banks.find((b) => String(b.id) === bankId);

  useEffect(() => {
    if (!complete) { setPreview(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      previewRange({ name, first, last, category, bank_id: bankId ? Number(bankId) : null, id: range?.id })
        .then((p) => { if (live) { setPreview(p); setError(null); } })
        .catch((e) => { if (live) { setPreview(null); setError(e.message); } });
    }, 150);
    return () => { live = false; clearTimeout(t); };
  }, [first, last, category, bankId, complete]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { name, first, last, category, bank_id: bankId ? Number(bankId) : null };
      onDone(range ? await changeRange(range.id, body) : await addRange(body));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  const n = preview?.count ?? 0;
  const label = fixed ? `${dates.label || rangeWords(first, last)} · Sort these days`
    : range ? 'Change this range' : 'Sort these days';
  const primary = busy ? 'Sorting…'
    : bank ? `Sort as ${category} · pay from ${bank.name}`
      : `${range ? 'Re-sort' : 'Sort'} ${n} purchase${n === 1 ? '' : 's'} as ${category}`;
  return (
    <DetailPanel label={label} overline={label} onClose={onClose} className="on-card rg-sheet">
      <h2 className="pk-h2">{range ? 'Change this range' : 'What were these days?'}</h2>
      {fixed ? (
        <p className="pk-muted">
          {(dates.label || rangeWords(first, last))}{dates.words ? ` · ${dates.words}` : ''}.
          Every purchase in them gets one category. You can undo it any time.
        </p>
      ) : (
        <p className="pk-muted">Give every purchase between two dates one category, like a trip.
          You can undo it any time.</p>
      )}
      <div className="txd-field">
        <label className="pk-label" htmlFor="rg-name">Name it (optional)</label>
        <input id="rg-name" type="text" maxLength={60} placeholder="Montréal trip" value={name}
               autoComplete="off" onChange={(e) => setName(e.target.value)} />
      </div>
      {!fixed && (
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
      )}
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
      {banks.length > 0 && (
        <div className="txd-field">
          <p className="pk-label">Paid from a treasure chest? Optional</p>
          <div className="pk-choices" role="radiogroup" aria-label="Paid from a treasure chest">
            <Choice name="rg-chest" checked={bankId === ''} onChange={() => setBankId('')}
                    label={`No, it counts in ${month}`} />
            {banks.map((b) => (
              <Choice key={b.id} name="rg-chest" checked={bankId === String(b.id)}
                      onChange={() => setBankId(String(b.id))} label={b.name}
                      description={`${money(Math.max(b.held ?? b.available ?? 0, 0))} in the chest`} />
            ))}
          </div>
        </div>
      )}
      {preview && (
        <div className="wwt-effect rg-summary" role="status" aria-live="polite">
          <p className="pk-label">{preview.title}</p>
          {preview.effect ? <p>{preview.effect}</p> : preview.mostly && <p>{preview.mostly}</p>}
          <p className="pk-muted">{preview.staying}</p>
        </div>
      )}
      {error && <p className="txd-error" role="alert">{error}</p>}
      <div className="txd-actions">
        <PButton disabled={busy || !complete || !preview || n === 0} onClick={save}>{primary}</PButton>
        <PButton variant="secondary" onClick={onClose}>{fixed ? 'Back' : 'Cancel'}</PButton>
      </div>
    </DetailPanel>
  );
}

/** Days sorted together (CAL-09): every range, under the calendar. */
export function SortedRanges({ ranges, onChange, onRemove }) {
  if (!ranges?.length) return null;
  return (
    <section className="hm-card rg-ranges" aria-labelledby="rg-ranges-title">
      <div className="rg-ranges-head">
        <h2 className="pk-h2" id="rg-ranges-title">Days sorted together</h2>
        <p className="pk-muted">Each range you sorted, with its total. Change one to sort it again,
          or remove it to put every purchase back.</p>
      </div>
      <div className="rg-list rg-grid">
        {ranges.map((r) => (
          <section key={r.id} className="rg-card" aria-label={r.name}>
            <div className="rg-card-top">
              <span>{r.name}</span>
              <span className="rg-total">{txAmount(r.total)}</span>
            </div>
            <p className="pk-label pk-muted">{rangeLine(r)}</p>
            <div className="rg-card-actions">
              <PButton variant="text" onClick={() => onChange(r)}>Change</PButton>
              <PButton variant="text" onClick={() => onRemove(r)}>Remove</PButton>
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
