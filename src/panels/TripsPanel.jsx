import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice } from '../components/ui.jsx';
import { addTrip, deleteTrip, getTrips, money, updateTrip } from '../api.js';

/**
 * Trips: declared date ranges whose spending is reclassified as Travel.
 *
 * Declared rather than detected, because the location in a card descriptor is
 * where the merchant is registered, not where you were — this ledger has
 * charges billed from Montreal and Quebec City months apart that are a
 * clothing chain's head office, not travel.
 */
export default function TripsPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ name: '', start_date: '', end_date: '' });

  async function load() {
    setError(null);
    try {
      setData(await getTrips());
    } catch (e) {
      setError(e);
    }
  }

  useEffect(() => { load(); }, []);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (editing) await updateTrip(editing, draft);
      else await addTrip(draft);
      setDraft({ name: '', start_date: '', end_date: '' });
      setEditing(null);
      await load();
      await onChanged?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(trip) {
    if (!window.confirm(
      `Remove "${trip.name}"? Its ${trip.transactions} transactions go back to `
      + 'their merchant categories.'
    )) return;
    setBusy(true);
    try {
      await deleteTrip(trip.id);
      await load();
      await onChanged?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function edit(trip) {
    setEditing(trip.id);
    setDraft({ name: trip.name, start_date: trip.start_date, end_date: trip.end_date });
  }

  if (!data && !error) return <Loading what="trips" />;

  const trips = data?.trips ?? [];
  const summary = data?.summary ?? {};

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      <Card
        title={editing ? 'Edit trip' : 'Add a trip'}
        hint="Every purchase between these dates becomes Travel, whatever the merchant"
      >
        <form className="controls" onSubmit={save}>
          <input
            type="text"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Where to?"
            aria-label="Trip name"
            style={{ flex: '1 1 200px' }}
            required
          />
          <label htmlFor="trip-start">From</label>
          <input
            id="trip-start" type="date" required
            value={draft.start_date}
            onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
          />
          <label htmlFor="trip-end">to</label>
          <input
            id="trip-end" type="date" required
            value={draft.end_date}
            onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
          />
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : editing ? 'Save changes' : 'Add trip'}
          </button>
          {editing && (
            <button type="button" className="btn quiet" onClick={() => {
              setEditing(null);
              setDraft({ name: '', start_date: '', end_date: '' });
            }}>
              Cancel
            </button>
          )}
        </form>
      </Card>

      {trips.length === 0 ? (
        <Notice>
          No trips yet. Holiday spending is scattered across Dining, Coffee,
          Transport and Shopping until you declare the dates — which also stops
          a trip inflating those categories and setting off a false
          &ldquo;you&apos;re eating out more&rdquo; finding.
        </Notice>
      ) : (
        <Card
          title={`${summary.count} trip${summary.count === 1 ? '' : 's'}`}
          hint={`${money(summary.total)} spent while away · ${money(summary.travel_spend)} now categorized as Travel`}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Trip</th>
                  <th>Dates</th>
                  <th className="r">Days</th>
                  <th className="r">Transactions</th>
                  <th className="r">Per day</th>
                  <th className="r">Total</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {trips.map((t) => (
                  <tr key={t.id}>
                    <td className="merchant">{t.name}</td>
                    <td className="muted">{t.start_date} → {t.end_date}</td>
                    <td className="r">{t.nights + 1}</td>
                    <td className="r">{t.transactions}</td>
                    <td className="r">{money(t.per_day)}</td>
                    <td className="r">{money(t.total, { cents: true })}</td>
                    <td className="r">
                      <button className="btn quiet" onClick={() => edit(t)}>Edit</button>
                      <button className="btn quiet" onClick={() => remove(t)}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 14, marginBottom: 0 }}>
            Card payments, transfers and fees are never reclassified, and a
            category you set by hand on a transaction stays yours.
          </p>
        </Card>
      )}
    </div>
  );
}
