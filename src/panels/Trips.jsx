import { useEffect, useState } from 'react';
import { deleteTrip, getTrips, previewTrip, saveTrip } from '../api.js';
import { Alert, DetailPanel, PButton, txAmount } from '../pearl/kit.jsx';
import { Field } from './GoalsParts.jsx';
import { shortDate } from './HomePanel.jsx';

/**
 * Trips (THL-174, 2026-10-13): "select a date range and have it sorted as
 * vacation". She names the trip and picks its dates, and its spending
 * becomes Travel on its own (2026-10-14: no list to tick). The panel says
 * how much moves, from which categories, and what stays as it is (bills,
 * pay, transfers…). The Trips list opens a trip to change or remove it.
 * See finance/trips.py.
 */

// What stays as it is, by the reason finance/trips.py gives.
const STAYING = [
  ['bill', 'bill or subscription', 'bills and subscriptions'],
  ['transfer', 'transfer or card payment', 'transfers and card payments'],
  ['money_in', 'deposit', 'deposits'],
  ['repayment', 'repayment', 'repayments'],
  ['yours', 'you sorted yourself', 'you sorted yourself'],
  ['excluded', 'you left out', 'you left out'],
  ['other_trip', 'in another trip', 'in another trip'],
];

/** "2 bills and subscriptions, 1 transfer or card payment". */
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

/** The summary under the dates: what moves, and what stays. */
export function TripSummary({ preview }) {
  const { count, total, categories, staying, staying_count: kept } = preview;
  return (
    <div className="trip-summary" aria-label="What happens">
      {count > 0 ? (
        <>
          <p className="pk-h3">{`${count} purchase${count === 1 ? '' : 's'} · ${txAmount(total)} becomes Travel`}</p>
          <p className="pk-label pk-muted">{mostlyWords(categories)}</p>
        </>
      ) : preview.in_dates === 0 ? (
        <p className="pk-h3">No transactions between these dates</p>
      ) : (
        <p className="pk-h3">Nothing here looks like trip spending</p>
      )}
      {kept > 0 && (
        <p className="pk-muted">{`Staying as ${kept === 1 ? 'it is' : 'they are'}: ${stayingWords(staying)}.`}</p>
      )}
      {count === 0 && preview.in_dates === 0 && (
        <p className="pk-muted">Pearl has nothing from your accounts on these days. If you paid
          with a card that isn’t connected, add it in Profile › Accounts; charges in these dates
          join the trip as they come in.</p>
      )}
    </div>
  );
}

const range = (t) => (t.start_date === t.end_date ? shortDate(t.start_date)
  : `${shortDate(t.start_date)} – ${shortDate(t.end_date)}`);

/** Mark a trip, or change one (`trip`). */
export function MarkTrip({ trip = null, onClose, onSaved }) {
  const [name, setName] = useState(trip?.name ?? '');
  const [start, setStart] = useState(trip?.start_date ?? '');
  const [end, setEnd] = useState(trip?.end_date ?? '');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!start || !end || end < start) { setPreview(null); return undefined; }
    let live = true;
    previewTrip(start, end, trip?.id ?? null).then((p) => {
      if (!live) return;
      setPreview(p);
      setError(null);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [start, end, trip?.id]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await saveTrip({ id: trip?.id, name: name.trim(), start, end });
      onSaved?.(r.trip);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };
  return (
    <DetailPanel label={trip ? `Change ${trip.name}` : 'Mark a trip'} overline="Trip" onClose={onClose}>
      <h1 className="pk-h2">{trip ? 'Change this trip' : 'Mark a trip'}</h1>
      <p className="pk-muted">What you spent while away becomes Travel, so it doesn’t make your
        usual Dining or Coffee look higher. Bills, pay and transfers stay as they are.</p>
      <Field label="Name" id="trip-name">
        <input id="trip-name" value={name} maxLength={60} placeholder="Costa Rica"
               onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="trip-dates">
        <Field label="From" id="trip-start">
          <input id="trip-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="To" id="trip-end">
          <input id="trip-end" type="date" value={end} min={start || undefined}
                 onChange={(e) => setEnd(e.target.value)} />
        </Field>
      </div>
      {preview && <TripSummary preview={preview} />}
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton disabled={busy || !name.trim() || !preview} onClick={save}>
        {busy ? 'Saving…' : trip ? 'Save changes' : 'Save trip'}
      </PButton>
    </DetailPanel>
  );
}

/** Her trips, to open one and change or remove it. */
export function TripsPanel({ onClose, onChanged }) {
  const [trips, setTrips] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState(null);
  const load = () => getTrips().then((r) => setTrips(r.trips)).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  if (open) {
    return (
      <MarkTrip trip={open === 'new' ? null : open} onClose={() => setOpen(null)}
                onSaved={() => { setOpen(null); load(); onChanged?.(); }} />
    );
  }
  return (
    <DetailPanel label="Trips" overline="Trips" onClose={onClose}>
      <h1 className="pk-h2">Trips</h1>
      {error && <Alert tone="caution">{error}</Alert>}
      {trips && trips.length === 0 && (
        <p className="pk-muted">No trips yet. Mark one and what you spent while away becomes Travel.</p>
      )}
      <ul className="trip-list">
        {(trips ?? []).map((t) => (
          <li key={t.id}>
            <button type="button" className="trip-open" onClick={() => setOpen(t)}>
              <span className="trip-row-text">
                <span>{t.name}</span>
                <span className="pk-label pk-muted">{t.count ? `${range(t)} · ${t.count} transaction${t.count === 1 ? '' : 's'}` : range(t)}</span>
              </span>
              <span className="trip-row-amount">{t.count ? txAmount(t.total) : 'No spending yet'}</span>
            </button>
            <PButton variant="text" onClick={() => deleteTrip(t.id).then(() => { load(); onChanged?.(); })
              .catch((e) => setError(e.message))}>
              Remove
            </PButton>
          </li>
        ))}
      </ul>
      <PButton variant="secondary" onClick={() => setOpen('new')}>Mark a trip</PButton>
    </DetailPanel>
  );
}
