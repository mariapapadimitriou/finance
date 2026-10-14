import { useEffect, useMemo, useState } from 'react';
import { deleteBulkEdit, getBulkEdits, previewBulkEdit, saveBulkEdit } from '../api.js';
import { Alert, DetailPanel, PButton, txAmount } from '../pearl/kit.jsx';
import { CategoryChips, groupCategories } from './CategoryPicker.jsx';
import { Field } from './GoalsParts.jsx';
import { shortDate } from './HomePanel.jsx';

/**
 * Sort a date range (2026-10-14; replaces trips): she names it, picks one
 * category and the first and last day, and every purchase in the range gets
 * that category. The panel says how much changes, from which categories,
 * and what stays as it is (pay, transfers…). Sorted together lists her
 * edits with running totals; open one to change it, or remove it to put
 * every row back. See finance/bulk_edits.py.
 */

// What stays as it is, by the reason finance/bulk_edits.py gives.
const STAYING = [
  ['transfer', 'transfer or card payment', 'transfers and card payments'],
  ['money_in', 'deposit', 'deposits'],
  ['repayment', 'repayment', 'repayments'],
  ['yours', 'you re-sorted by hand', 'you re-sorted by hand'],
  ['excluded', 'you left out', 'you left out'],
  ['other_edit', 'in another range you sorted', 'in another range you sorted'],
];

/** "2 deposits, 1 transfer or card payment". */
export function stayingWords(staying = {}) {
  return STAYING.filter(([k]) => staying[k])
    .map(([k, one, many]) => `${staying[k]} ${staying[k] === 1 ? one : many}`).join(', ');
}

/** "Mostly Lodging, Dining and Transport". */
export function mostlyWords(categories = []) {
  const top = categories.slice(0, 3).map((c) => c.category);
  if (!top.length) return '';
  return `Mostly ${top.length === 1 ? top[0] : `${top.slice(0, -1).join(', ')} and ${top.at(-1)}`}`;
}

/** The summary under the dates: what changes, and what stays. */
export function RangeSummary({ preview }) {
  const { count, total, category, categories, staying, staying_count: kept } = preview;
  return (
    <div className="be-summary" aria-label="What happens">
      {count > 0 ? (
        <>
          <p className="pk-h3">
            {`${count} purchase${count === 1 ? '' : 's'} · ${txAmount(total)} become${count === 1 ? 's' : ''} ${category}`}
          </p>
          <p className="pk-label pk-muted">{mostlyWords(categories)}</p>
        </>
      ) : preview.in_dates === 0 ? (
        <p className="pk-h3">No transactions between these dates</p>
      ) : (
        <p className="pk-h3">No purchases to sort between these dates</p>
      )}
      {kept > 0 && (
        <p className="pk-muted">{`Staying as ${kept === 1 ? 'it is' : 'they are'}: ${stayingWords(staying)}.`}</p>
      )}
      {count === 0 && preview.in_dates === 0 && (
        <p className="pk-muted">Pearl has nothing from your accounts on these days. If you paid
          with a card that isn’t connected, add it in Profile › Accounts.</p>
      )}
    </div>
  );
}

const range = (e) => (e.start_date === e.end_date ? shortDate(e.start_date)
  : `${shortDate(e.start_date)} – ${shortDate(e.end_date)}`);

/** Sort a date range, or change an edit (`edit`). */
export function SortRange({ edit = null, categories = [], onClose, onSaved }) {
  const [name, setName] = useState(edit?.name ?? '');
  const [category, setCategory] = useState(edit?.category ?? '');
  const [start, setStart] = useState(edit?.start_date ?? '');
  const [end, setEnd] = useState(edit?.end_date ?? '');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const groups = useMemo(() => groupCategories(categories, {
    only: (c) => ['essentials', 'lifestyle'].includes(c.group),
  }), [categories]);

  useEffect(() => {
    if (!start || !end || end < start || !category) { setPreview(null); return undefined; }
    let live = true;
    previewBulkEdit({ start, end, category, edit_id: edit?.id ?? null }).then((p) => {
      if (!live) return;
      setPreview(p);
      setError(null);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [start, end, category, edit?.id]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await saveBulkEdit({ id: edit?.id, name: name.trim(), category, start, end });
      onSaved?.(r.edit);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  return (
    <DetailPanel label={edit ? `Change ${edit.name}` : 'Sort a date range'} overline="Sort together"
                 onClose={onClose}>
      <h1 className="pk-h2">{edit ? 'Change this range' : 'Sort a date range'}</h1>
      <p className="pk-muted">Every purchase between the dates gets the category you choose.
        Pay and transfers stay as they are.</p>
      <Field label="Name" id="be-name">
        <input id="be-name" value={name} maxLength={60} placeholder="Costa Rica"
               onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="be-dates">
        <Field label="From" id="be-start">
          <input id="be-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="To" id="be-end">
          <input id="be-end" type="date" value={end} min={start || undefined}
                 onChange={(e) => setEnd(e.target.value)} />
        </Field>
      </div>
      <div className="be-category">
        <p className="pk-label">Sort everything as</p>
        <CategoryChips groups={groups} value={category} onChange={setCategory}
                       label="Sort everything as" />
      </div>
      {preview && <RangeSummary preview={preview} />}
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton disabled={busy || !name.trim() || !category || !preview} onClick={save}>
        {busy ? 'Saving…' : edit ? 'Save changes' : 'Sort them'}
      </PButton>
    </DetailPanel>
  );
}

/** Her edits with running totals; open one to change or remove it. */
export function BulkEditsPanel({ categories = [], onClose, onChanged }) {
  const [edits, setEdits] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState(null);
  const load = () => getBulkEdits().then((r) => setEdits(r.edits)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  if (open) {
    return (
      <SortRange edit={open === 'new' ? null : open} categories={categories}
                 onClose={() => setOpen(null)}
                 onSaved={() => { setOpen(null); load(); onChanged?.(); }} />
    );
  }
  return (
    <DetailPanel label="Sorted together" overline="Sort together" onClose={onClose}>
      <h1 className="pk-h2">Sorted together</h1>
      {error && <Alert tone="caution">{error}</Alert>}
      {edits && edits.length === 0 && (
        <p className="pk-muted">Nothing yet. Sort a date range and every purchase in it gets one
          category.</p>
      )}
      <ul className="be-list">
        {(edits ?? []).map((e) => (
          <li key={e.id}>
            <button type="button" className="be-open" onClick={() => setOpen(e)}>
              <span className="be-row-text">
                <span>{e.name}</span>
                <span className="pk-label pk-muted">
                  {`${range(e)} · ${e.category}${e.count ? ` · ${e.count} purchase${e.count === 1 ? '' : 's'}` : ''}`}
                </span>
              </span>
              <span className="be-row-amount">{e.count ? txAmount(e.total) : 'Nothing yet'}</span>
            </button>
            <PButton variant="text" onClick={() => deleteBulkEdit(e.id).then(() => { load(); onChanged?.(); })
              .catch((err) => setError(err.message))}>
              Remove
            </PButton>
          </li>
        ))}
      </ul>
      <PButton variant="secondary" onClick={() => setOpen('new')}>Sort a date range</PButton>
    </DetailPanel>
  );
}
