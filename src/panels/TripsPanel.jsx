import { useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice } from '../components/ui.jsx';
import {
  addTrip, dateLabel, deleteTrip, getTripSuggestions, getTrips, money, updateTrip,
} from '../api.js';

/**
 * Trips: declared date ranges whose spending is reclassified as Travel.
 *
 * Declared rather than detected from *location*, because the place in a card
 * descriptor is where the merchant is registered, not where you were — this
 * ledger has charges billed from Montreal and Quebec City months apart that
 * are a clothing chain's head office, not travel.
 *
 * Currency is a different matter. A charge converted from another currency
 * was made in that currency, which is not a guess, so a run of days whose
 * spending was mostly foreign is offered as a suggestion. Still only a
 * suggestion: declaring a trip recategorises every charge inside it, and the
 * dates are proposed rather than applied.
 */
export default function TripsPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ name: '', start_date: '', end_date: '' });

  /** Take a suggestion as-is. The dates came from the charges themselves. */
  async function accept(sug) {
    setBusy(true);
    setError(null);
    try {
      await addTrip({ name: sug.name, start_date: sug.start_date,
                      end_date: sug.end_date });
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function load() {
    setError(null);
    try {
      setData(await getTrips());
      setSuggestions((await getTripSuggestions().catch(() => null))?.suggestions ?? []);
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

      {suggestions.length > 0 && (
        <Card title={`${suggestions.length} trip${suggestions.length === 1 ? '' : 's'} found in your spending`}
              hint="Days where most of what you bought was charged in another currency">
          <div className="stack" style={{ gap: 14 }}>
            {suggestions.map((sug) => (
              <div key={sug.start_date} className="row"
                   style={{ justifyContent: 'space-between', alignItems: 'flex-start',
                            gap: 16, flexWrap: 'wrap' }}>
                <div style={{ minWidth: 0 }}>
                  <div className="merchant">
                    {sug.name}
                    {sug.places.length > 1 && (
                      <span className="muted"> · {sug.places.slice(1).join(', ')}</span>
                    )}
                  </div>
                  <div className="desc">
                    {dateLabel(sug.start_date)} – {dateLabel(sug.end_date)} ·{' '}
                    {sug.days} days · {sug.charges} charges ·{' '}
                    {money(sug.total)} in {sug.currencies.join(' and ')}
                  </div>
                </div>
                <button className="btn primary" disabled={busy}
                        onClick={() => accept(sug)}>
                  Add this trip
                </button>
              </div>
            ))}
          </div>
          <p className="assumption" style={{ marginBottom: 0 }}>
            Found by currency, not by the place in a descriptor: a charge
            converted from colónes really was made in colónes, whereas a
            merchant registered in Montreal may never have been visited.
            Adding one reclassifies every charge between those dates as
            Travel, so check the dates before you do — they can be edited
            afterwards.
          </p>
        </Card>
      )}

      {/* With nothing declared there is no table worth drawing. The notice
          makes the case for declaring one; when a suggestion is already
          making that case, neither is needed. */}
      {trips.length === 0 ? (suggestions.length === 0 && (
        <Notice>
          No trips yet. Holiday spending is scattered across Dining, Coffee,
          Transport and Shopping until you declare the dates — which also stops
          a trip inflating those categories and setting off a false
          &ldquo;you&apos;re eating out more&rdquo; finding.
        </Notice>
      )) : (
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
