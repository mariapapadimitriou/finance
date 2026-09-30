import { useCallback, useEffect, useState } from 'react';
import { Card, ErrorNote, Loading, Notice, StatusPill } from '../components/ui.jsx';
import {
  createLinkToken, exchangePublicToken, getPlaidItems, syncPlaid, unlinkBank,
} from '../api.js';

const LINK_SCRIPT = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';

/**
 * Plaid Link, loaded from Plaid's CDN rather than bundled.
 *
 * Plaid require the script to be loaded from their domain so fixes and
 * institution changes reach every integration without a redeploy — a bundled
 * copy would go stale against banks that change their login. Loaded on demand
 * rather than at page load, so nothing is fetched from Plaid unless you
 * actually open this tab.
 */
function loadPlaidScript() {
  if (window.Plaid) return Promise.resolve(window.Plaid);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${LINK_SCRIPT}"]`);
    if (existing) {
      existing.addEventListener('load', () => resolve(window.Plaid));
      existing.addEventListener('error', () => reject(new Error('Plaid Link failed to load.')));
      return;
    }
    const tag = document.createElement('script');
    tag.src = LINK_SCRIPT;
    tag.onload = () => resolve(window.Plaid);
    tag.onerror = () => reject(new Error('Plaid Link failed to load.'));
    document.head.appendChild(tag);
  });
}

export default function BanksPanel({ onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await getPlaidItems());
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function startLink() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const [Plaid, { link_token: token }] = await Promise.all([
        loadPlaidScript(), createLinkToken(),
      ]);

      const handler = Plaid.create({
        token,
        // The public token is single-use and useless on its own; the access
        // token it becomes is created and kept server-side, and never reaches
        // this page.
        onSuccess: async (publicToken, metadata) => {
          setBusy(true);
          try {
            const r = await exchangePublicToken(
              publicToken, metadata?.institution?.name || '');
            setResult(r.sync ?? { imported: 0 });
            await load();
            await onChanged?.();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        },
        onExit: (err) => {
          setBusy(false);
          // Closing the window deliberately is not an error worth shouting
          // about; a real failure from Plaid is.
          if (err) setError(new Error(err.display_message || err.error_message
                                      || 'Linking was cancelled.'));
        },
      });
      handler.open();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  async function sync() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await syncPlaid();
      setResult(r);
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    if (!window.confirm(
      `Disconnect ${item.institution || 'this bank'}? Transactions already `
      + 'imported stay in your ledger; only the live connection goes.'
    )) return;
    setBusy(true);
    try {
      await unlinkBank(item.item_id);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!data && !error) return <Loading what="your bank connections" />;
  if (!data) return <ErrorNote error={error} onRetry={load} />;

  const { configured, environment, encryption_ready: encrypted, items } = data;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />

      {!configured && (
        <Notice>
          <strong>Plaid isn&apos;t set up on this deployment yet.</strong> Add{' '}
          <code>PLAID_CLIENT_ID</code>, <code>PLAID_SECRET</code> and{' '}
          <code>PLAID_ENV</code> to the project&apos;s environment variables and
          redeploy. Until then you can still import statements on the Import tab.
        </Notice>
      )}

      {configured && !encrypted && (
        <Notice kind="error">
          <strong>No encryption key is set.</strong> A bank token is a live
          credential, so linking is refused until <code>SPENDIE_SECRET_KEY</code>{' '}
          exists to encrypt it before it reaches the database.
        </Notice>
      )}

      {configured && environment === 'sandbox' && (
        <Notice>
          Running against Plaid&apos;s <strong>sandbox</strong>, so you&apos;ll
          get made-up test transactions rather than your own. Switch{' '}
          <code>PLAID_ENV</code> to <code>production</code> when you&apos;re ready
          for the real thing.
        </Notice>
      )}

      <Card
        title="Connected banks"
        hint="Linked through Plaid — transactions arrive without downloading a statement"
        actions={
          <div className="row" style={{ gap: 8 }}>
            {items.length > 0 && (
              <button className="btn" onClick={sync} disabled={busy || !configured}>
                {busy ? 'Working…' : 'Sync now'}
              </button>
            )}
            <button className="btn primary" onClick={startLink}
                    disabled={busy || !configured || !encrypted}>
              + Connect a bank
            </button>
          </div>
        }
      >
        {items.length === 0 ? (
          <p className="small muted" style={{ margin: 0 }}>
            Nothing connected yet. Connecting a card pulls its history in and
            keeps it current, so you stop downloading statements by hand. Your
            bank login goes to Plaid, never to Spendie — what gets stored here
            is a token that can read transactions and nothing else.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Bank</th>
                  <th>Last synced</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.item_id}>
                    <td className="merchant">{it.institution || 'Linked bank'}</td>
                    <td className="muted">
                      {it.last_synced ? it.last_synced.replace('T', ' ').slice(0, 16)
                                      : 'not yet'}
                    </td>
                    <td>
                      {it.last_error ? (
                        <StatusPill state="critical">Needs attention</StatusPill>
                      ) : it.synced_before ? (
                        <StatusPill state="good">Connected</StatusPill>
                      ) : (
                        <StatusPill state="warning">Awaiting first sync</StatusPill>
                      )}
                      {it.last_error && (
                        <div className="desc" title={it.last_error}>{it.last_error}</div>
                      )}
                    </td>
                    <td className="r">
                      <button className="btn quiet" disabled={busy}
                              onClick={() => remove(it)}>Disconnect</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {result && (
          <Notice kind="good" >
            {result.imported > 0
              ? `Brought in ${result.imported} new transaction${result.imported === 1 ? '' : 's'}.`
              : 'Already up to date — nothing new since the last sync.'}
            {result.errors?.length > 0 && (
              <> {result.errors.length} connection(s) reported a problem.</>
            )}
          </Notice>
        )}

        <p className="assumption" style={{ marginBottom: 0 }}>
          Only what changed since the last sync is fetched, so syncing often is
          cheap. When a pending charge posts, the pending version is removed
          rather than left beside the real one.
        </p>
      </Card>
    </div>
  );
}
