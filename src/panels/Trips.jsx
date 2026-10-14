import { useEffect, useState } from 'react';
import { deleteTrip, getTrips, previewTrip, saveTrip } from '../api.js';
import { Alert, DetailPanel, PButton, txAmount } from '../pearl/kit.jsx';
import { Field } from './GoalsParts.jsx';
import { shortDate } from './HomePanel.jsx';

/**
 * Trips (THL-174, 2026-10-13): "select a date range and have it sorted as
 * vacation". She names the trip and picks its dates; every transaction in
 * them is listed, ticked unless it isn't trip spending (bills, pay, card
 * payments…, with the reason), and Save moves the ticked ones to Travel.
 * The Trips list opens a trip to change or remove it. See finance/trips.py.
 */

const range = (t) => (t.start_date === t.end_date ? shortDate(t.start_date)
  : `${shortDate(t.start_date)} – ${shortDate(t.end_date)}`);

/** Mark a trip, or change one (`trip`). */
export function MarkTrip({ trip = null, onClose, onSaved }) {
  const [name, setName] = useState(trip?.name ?? '');
  const [start, setStart] = useState(trip?.start_date ?? '');
  const [end, setEnd] = useState(trip?.end_date ?? '');
  const [rows, setRows] = useState(null);
  const [ticked, setTicked] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!start || !end || end < start) { setRows(null); return undefined; }
    let live = true;
    previewTrip(start, end, trip?.id ?? null).then((p) => {
      if (!live) return;
      setRows(p.rows);
      setTicked(new Set(p.rows.filter((r) => r.ticked).map((r) => r.id)));
      setError(null);
    }).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [start, end, trip?.id]);

  const total = (rows ?? []).filter((r) => ticked.has(r.id)).reduce((s, r) => s + r.amount, 0);
  const toggle = (id) => setTicked((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await saveTrip({ id: trip?.id, name: name.trim(), start, end }, [...ticked]);
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
        usual Dining or Coffee look higher. Bills and pay stay as they are.</p>
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
      {rows && (
        <>
          <p className="pk-label">
            {`${ticked.size} of ${rows.length} transactions · ${txAmount(total)} to Travel`}
          </p>
          <ul className="trip-rows" aria-label="Transactions in these dates">
            {rows.map((r) => (
              <li key={r.id}>
                <label className="txd-check">
                  <input type="checkbox" checked={ticked.has(r.id)} onChange={() => toggle(r.id)} />
                  <span className="trip-row-text">
                    <span>{r.merchant}</span>
                    <span className="pk-label pk-muted">
                      {[shortDate(r.date), r.why_not].filter(Boolean).join(' · ')}
                    </span>
                  </span>
                  <span className="trip-row-amount">{txAmount(Math.abs(r.amount), { inflow: r.amount < 0 })}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton disabled={busy || !name.trim() || !rows} onClick={save}>
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
                <span className="pk-label pk-muted">{`${range(t)} · ${t.count} transactions`}</span>
              </span>
              <span className="trip-row-amount">{txAmount(t.total)}</span>
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
