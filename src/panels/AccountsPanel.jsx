import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import {
  dateLabel, deleteAccount, getAccounts, getDuplicateAudit, money, resetLedger,
} from '../api.js';

/**
 * Every account in the ledger, and the two ways it can hold something twice.
 *
 * Linking a bank hands over chequing, savings and investment accounts
 * alongside the card. Syncing now keeps only the cards, but anything pulled in
 * before that can be removed here — and a closed card's imported statements
 * can stay exactly as they are, since nothing will ever add to them.
 */
export default function AccountsPanel({ onChanged }) {
  const [accounts, setAccounts] = useState(null);
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [a, d] = await Promise.all([
        getAccounts(), getDuplicateAudit().catch(() => null),
      ]);
      setAccounts(a.accounts ?? []);
      setAudit(d);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function remove(account) {
    if (!window.confirm(
      `Remove "${account.account_name}" and all ${account.transactions} of its `
      + 'transactions? This can\'t be undone — if it\'s a connected account it '
      + 'will come back on the next sync unless you disconnect the bank too.'
    )) return;
    setBusy(true);
    try {
      await deleteAccount(account.account_id);
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!accounts && !error) return <Loading what="your accounts" />;
  if (!accounts) return <ErrorNote error={error} onRetry={load} />;

  const notCards = accounts.filter((a) => !a.is_card);
  const total = accounts.reduce((n, a) => n + a.transactions, 0);
  const overlaps = audit?.account_overlaps ?? [];
  const dupes = audit?.duplicates ?? [];

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      {notCards.length > 0 && (
        <Notice>
          <strong>
            {notCards.length} account{notCards.length === 1 ? '' : 's'} here
            {notCards.length === 1 ? ' is' : ' are'} not a credit card.
          </strong>{' '}
          Syncing now skips everything but cards, so nothing new will arrive
          from {notCards.length === 1 ? 'it' : 'them'} — but what was already
          imported is still counted. A chequing account records the payment
          that settles the card, so leaving it in counts the same money twice.
        </Notice>
      )}

      <Card title="Accounts" hint="Everything the ledger has transactions for">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Kind</th>
                <th>Range</th>
                <th className="r">Rows</th>
                <th className="r">Spend</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.account_id}>
                  <td className="merchant">
                    {a.account_name}
                    <div className="desc">
                      {a.source === 'plaid' ? 'connected through Plaid'
                        : a.source === 'manual' ? 'added by hand'
                        : 'imported from statements'}
                    </div>
                  </td>
                  <td>
                    {a.is_card
                      ? <StatusPill state="good">Card</StatusPill>
                      : <StatusPill state="warning">
                          {a.plaid_subtype || a.plaid_type || 'not a card'}
                        </StatusPill>}
                  </td>
                  <td className="muted">
                    {dateLabel(a.first_date)} – {dateLabel(a.last_date)}
                  </td>
                  <td className="r">{a.transactions}</td>
                  <td className="r num">{money(a.total_spend)}</td>
                  <td className="r">
                    <button className="btn quiet" disabled={busy}
                            onClick={() => remove(a)}>Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="assumption" style={{ marginBottom: 0 }}>
          Removing an account deletes its transactions. If the account is still
          connected on the Banks tab, the next sync brings them back —
          disconnect the bank first, or turn the account off at the source.
        </p>
      </Card>

      <StartFresh total={total} busy={busy} setBusy={setBusy}
                  setError={setError} onDone={async () => {
                    await load(); await onChanged?.();
                  }} />

      <Card title="Possible overlap"
            hint="The same purchase arriving under two different accounts">
        {overlaps.length === 0 && dupes.length === 0 ? (
          <Notice kind="good">
            Nothing overlapping. No two accounts share a date range and a set of
            amounts, and no single charge appears under two of them within five
            days.
          </Notice>
        ) : (
          <>
            {overlaps.length > 0 && (
              <>
                <p className="small muted" style={{ marginTop: 0 }}>
                  These pairs of accounts cover the same months and share
                  amounts. A high overlap usually means one card was imported
                  twice — from statements and again through Plaid.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>These two accounts</th>
                        <th className="r">Shared amounts</th>
                        <th className="r">Overlap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overlaps.map((o, i) => (
                        <tr key={i}>
                          <td className="merchant">
                            {o.accounts[0].account} ({o.accounts[0].source})
                            <div className="desc">
                              and {o.accounts[1].account} ({o.accounts[1].source})
                            </div>
                          </td>
                          <td className="r">{o.shared_amounts}</td>
                          <td className="r">
                            {Math.round(o.overlap * 100)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {dupes.length > 0 && (
              <>
                <div className="tile-label" style={{ marginTop: 18 }}>
                  {audit.duplicate_count} charge
                  {audit.duplicate_count === 1 ? '' : 's'} to look at
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Charge</th><th>Also on</th>
                        <th className="r">Amount</th><th>Match</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dupes.slice(0, 40).map((d, i) => (
                        <tr key={i}>
                          <td className="merchant">
                            {d.rows[0].merchant}
                            <div className="desc">
                              {dateLabel(d.rows[0].date)} · {d.rows[0].account}{' '}
                              ({d.rows[0].source})
                            </div>
                          </td>
                          <td className="merchant">
                            {d.rows[1].merchant}
                            <div className="desc">
                              {dateLabel(d.rows[1].date)} · {d.rows[1].account}{' '}
                              ({d.rows[1].source})
                            </div>
                          </td>
                          <td className="r num">{money(d.amount, { cents: true })}</td>
                          <td>
                            <StatusPill
                              state={d.same_merchant && d.days_apart <= 1
                                ? 'critical' : 'warning'}>
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

        <p className="assumption" style={{ marginBottom: 0 }}>
          {audit?.note ?? ''} To clear a whole duplicated account, remove it
          above; to drop a single charge, use the Transactions tab.
        </p>
      </Card>
    </div>
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
function StartFresh({ total, busy, setBusy, setError, onDone }) {
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
          hint="Empty the ledger and everything worked out from it"
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
          The ledger currently holds {total.toLocaleString()} transaction
          {total === 1 ? '' : 's'}. Starting fresh removes all of them, along
          with your budgets, trips, buckets, merchant corrections and dismissed
          findings. Your password and bank credentials are untouched.
        </p>
      ) : (
        <form onSubmit={go}>
          <Notice kind="error">
            <strong>This cannot be undone.</strong> It removes{' '}
            {total.toLocaleString()} transaction{total === 1 ? '' : 's'}, every
            budget, trip, bucket, merchant correction and dismissed finding.
            What stays: your password, your Plaid credentials, and — unless you
            untick below — your bank connections.
          </Notice>

          <label className="row" style={{ marginTop: 14, gap: 8 }}>
            <input type="checkbox" checked={keepBanks}
                   onChange={(e) => setKeepBanks(e.target.checked)} />
            <span className="small">
              Keep TD and Wealthsimple connected. Their sync position is
              rewound either way, so the next sync re-fetches the full history
              rather than reporting nothing new against an empty ledger.
            </span>
          </label>

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
