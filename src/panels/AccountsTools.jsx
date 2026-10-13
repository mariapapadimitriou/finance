import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Notice, StatusPill } from '../components/ui.jsx';
import {
  dateLabel, getDuplicateAudit, getLedgerStart, money, recategorizeAll, resetLedger,
  setLedgerStart,
} from '../api.js';

/**
 * The housekeeping that lived on the old Accounts page and has no screen in
 * the Pearl handoff yet: where trends start counting, re-checking every
 * category, starting fresh, and charges that may be on two accounts. Kept,
 * folded under the Accounts list (AM-01), until "Your data" is designed.
 */
export default function AccountsTools({ total, connected, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  return (
    <details className="pf-more">
      <summary>Fixing your history</summary>
      <div className="stack">
        <ErrorNote error={error} />
        <TrendBasis onChanged={onChanged} />
        <StartFresh total={total} connected={connected} busy={busy} setBusy={setBusy}
                    setError={setError} onDone={onChanged} />
        <Overlap />
      </div>
    </details>
  );
}

/** Charges that may be on two accounts at once. */
function Overlap() {
  const [audit, setAudit] = useState(null);
  useEffect(() => { getDuplicateAudit().then(setAudit).catch(() => {}); }, []);
  if (!audit) return null;
  const overlaps = audit.account_overlaps ?? [];
  const dupes = audit.duplicates ?? [];
  return (
    <Card title="Possible overlap">
      {overlaps.length === 0 && dupes.length === 0 ? (
        <Notice kind="good">Nothing overlapping</Notice>
      ) : (
        <>
          {overlaps.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>These two accounts</th><th className="r">Shared amounts</th>
                    <th className="r">Overlap</th></tr>
                </thead>
                <tbody>
                  {overlaps.map((o, i) => (
                    <tr key={i}>
                      <td className="merchant">
                        {o.accounts[0].account} ({o.accounts[0].source})
                        <div className="desc">and {o.accounts[1].account} ({o.accounts[1].source})</div>
                      </td>
                      <td className="r">{o.shared_amounts}</td>
                      <td className="r">{Math.round(o.overlap * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {dupes.length > 0 && (
            <>
              <div className="tile-label" style={{ marginTop: 18 }}>
                {audit.duplicate_count} charge{audit.duplicate_count === 1 ? '' : 's'} to look at
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Charge</th><th>Also on</th><th className="r">Amount</th><th>Match</th></tr>
                  </thead>
                  <tbody>
                    {dupes.slice(0, 40).map((d, i) => (
                      <tr key={i}>
                        <td className="merchant">
                          {d.rows[0].merchant}
                          <div className="desc">{dateLabel(d.rows[0].date)} · {d.rows[0].account} ({d.rows[0].source})</div>
                        </td>
                        <td className="merchant">
                          {d.rows[1].merchant}
                          <div className="desc">{dateLabel(d.rows[1].date)} · {d.rows[1].account} ({d.rows[1].source})</div>
                        </td>
                        <td className="r num">{money(d.amount, { cents: true })}</td>
                        <td>
                          <StatusPill state={d.same_merchant && d.days_apart <= 1 ? 'critical' : 'warning'}>
                            {d.same_merchant ? 'Same merchant' : 'Amount only'}
                          </StatusPill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </Card>
  );
}

/**
 * Emptying the ledger.
 *
 * Irreversible against a hosted database, so it asks for the word in writing
 * rather than offering a button that does it on one click. The list of what
 * goes is spelled out because "start fresh" means different things to
 * different people, and the difference here is a year of spending.
 */
function StartFresh({ total, connected = [], busy, setBusy, setError, onDone }) {
  const [open, setOpen] = useState(false);
  const [word, setWord] = useState('');
  const [keepBanks, setKeepBanks] = useState(true);
  const [done, setDone] = useState(null);

  async function go(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setDone(await resetLedger(keepBanks));
      setWord('');
      setOpen(false);
      await onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Start fresh"
          actions={!open && (
            <button className="btn" onClick={() => setOpen(true)}>
              Start fresh…
            </button>
          )}>
      {done ? (
        <Notice kind="good">
          Removed {done.transactions_removed} transaction
          {done.transactions_removed === 1 ? '' : 's'}. {done.note}
        </Notice>
      ) : !open ? (
        <p className="small muted" style={{ margin: 0 }}>
          {total.toLocaleString()} transaction{total === 1 ? '' : 's'}
        </p>
      ) : (
        <form onSubmit={go}>
          <Notice kind="error">
            <strong>This cannot be undone.</strong> It removes{' '}
            {total.toLocaleString()} transaction{total === 1 ? '' : 's'}, every
            budget, trip, merchant correction and dismissed finding. What
            stays: your password, your plan and your piggy banks
            {connected.length > 0 && ', and — unless you untick below — your bank connections'}.
          </Notice>

          {/* Only offered when there is something to keep. It used to name two
              institutions from the author's own ledger, shown to everyone
              including someone with nothing connected at all — on the most
              irreversible control in the app. */}
          {connected.length > 0 && (
            <label className="row" style={{ marginTop: 14, gap: 8 }}>
              <input type="checkbox" checked={keepBanks}
                     onChange={(e) => setKeepBanks(e.target.checked)} />
              <span className="small">
                Keep {connected.length === 1 ? 'this connection' : `these ${connected.length} connections`}:{' '}
                {connected.slice(0, 3).join(', ')}
                {connected.length > 3 && ` and ${connected.length - 3} more`}.
                Their sync position is rewound either way, so the next sync
                re-fetches the full history rather than reporting nothing new
                against an empty ledger.
              </span>
            </label>
          )}
          {connected.length > 0 && !keepBanks && (
            <p className="small" style={{ margin: '10px 0 0' }}>
              <strong>Disconnects every bank, here and at Plaid.</strong> Link
              each bank once afterwards, above.
            </p>
          )}

          <div className="controls" style={{ marginTop: 14 }}>
            <label htmlFor="erase">Type <code>erase</code> to confirm</label>
            <input id="erase" type="text" value={word} autoComplete="off"
                   onChange={(e) => setWord(e.target.value)}
                   style={{ width: 140 }} />
            <button className="btn" type="submit"
                    disabled={busy || word.trim().toLowerCase() !== 'erase'}>
              {busy ? 'Erasing…' : 'Erase everything'}
            </button>
            <button type="button" className="btn quiet"
                    onClick={() => { setOpen(false); setWord(''); }}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}

/**
 * The two reasons a total can be wrong about you.
 *
 * Both are about history rather than about any one transaction, which is why
 * they sit together.
 *
 * A month where only some cards were imported reads as restraint. It is not —
 * it is a month with cards missing, and averaged in with the complete ones it
 * drags every trend down and quietly flatters the picture. The honest fix is
 * to say where the complete record starts.
 *
 * That date has to persist, not just delete. A fresh Plaid link backfills two
 * years, so a one-time deletion would be undone by the next sync; the date is
 * applied to everything that arrives afterwards too.
 *
 * The second: categorization rules improve after rows are already stored, and
 * nothing re-runs them on their own. The rule that matters most here is the
 * one that keeps a card payment out of spending — a payment is negative, so
 * misreading it does not merely mislabel a row, it subtracts from the month.
 */
function TrendBasis({ onChanged }) {
  const [info, setInfo] = useState(null);
  const [start, setStart] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const i = await getLedgerStart();
      setInfo(i);
      setStart(i.start || '');
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save(trim) {
    if (trim && !window.confirm(
      `Remove every transaction before ${start}? This can't be undone, and `
      + 'the date is remembered — later syncs and imports will skip those '
      + 'months too, until you change it back.'
    )) return;
    setBusy(true);
    setError(null);
    try {
      const r = await setLedgerStart(start, trim);
      setDone(trim
        ? `Removed ${r.removed} transaction${r.removed === 1 ? '' : 's'} from before ${r.start}.`
        : (r.start ? `Counting from ${r.start}.` : 'No start date — everything counts.'));
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function recheck() {
    setBusy(true);
    setError(null);
    try {
      const r = await recategorizeAll();
      setDone(`Re-checked every transaction; ${r.updated} changed category.`);
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!info) return null;

  const changed = (start || '') !== (info.start || '');
  const wouldRemove = start && info.earliest && start > info.earliest;

  return (
    <Card title="What counts toward trends">
      <ErrorNote error={error} />

      <p className="small muted" style={{ marginTop: 0 }}>
        {info.total.toLocaleString()} transaction{info.total === 1 ? '' : 's'}
        {info.earliest && <> · {info.earliest} – {info.latest}</>}
      </p>

      <div className="controls">
        <label htmlFor="ledger-start">Count from</label>
        <input id="ledger-start" type="date" value={start}
               onChange={(e) => setStart(e.target.value)} />
        <button className="btn" type="button" disabled={busy || !changed}
                onClick={() => save(false)}>
          Save date
        </button>
        <button className="btn" type="button"
                disabled={busy || !start || !wouldRemove}
                onClick={() => save(true)}>
          {busy ? 'Working…' : 'Save and remove earlier'}
        </button>
      </div>

      {done && <Notice kind="good">{done}</Notice>}


      <div className="controls" style={{ marginTop: 4 }}>
        <button className="btn quiet" type="button" disabled={busy}
                onClick={recheck}>
          Re-check categories
        </button>
      </div>
    </Card>
  );
}
