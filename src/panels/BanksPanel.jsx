import { useCallback, useEffect, useState } from 'react';
import {
  Card, ErrorNote, GoTo, Loading, Notice, StatusPill, } from '../components/ui.jsx';
import {
  checkPlaidKeys, createLinkToken, exchangePublicToken, getPlaidItems,
  syncPlaid, unlinkBank,
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

export default function BanksPanel({ onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [keyCheck, setKeyCheck] = useState(null);

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

  async function check() {
    setBusy(true);
    setError(null);
    setKeyCheck(null);
    try {
      setKeyCheck(await checkPlaidKeys());
    } catch (e) {
      setError(e);
    } finally {
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

  const { configured, environment, encryption_ready: encrypted, items,
          credentials } = data;

  return (
    <div className="stack">
      <ErrorNote error={error} onRetry={load} />
      {error && configured && (
        <Credentials shape={credentials} environment={environment}
                     check={check} checking={busy} result={keyCheck} />
      )}

      {!configured && (
        <Notice>
          <strong>Plaid isn&apos;t set up</strong>
          {onTab && (
            <> · <button className="link" onClick={() => onTab('import')}>
              Import a file
            </button></>
          )}
        </Notice>
      )}

      {configured && !encrypted && (
        <Notice kind="error">
          <strong>SPENDIE_SECRET_KEY isn&apos;t set</strong>
        </Notice>
      )}

      {configured && !['sandbox', 'production'].includes(environment) && (
        <Notice kind="error">
          <strong>PLAID_ENV &ldquo;{environment}&rdquo; isn&apos;t valid</strong>{' '}
          · use <code>sandbox</code> or <code>production</code>
        </Notice>
      )}

      {configured && environment === 'sandbox' && (
        <Notice>
          Plaid <strong>sandbox</strong> · test data
        </Notice>
      )}

      <Card
        title="Connected banks"
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
          <p className="muted" style={{ margin: 0 }}>Nothing connected</p>
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
              : 'Up to date'}
            {result.errors?.length > 0 && (
              <> {result.errors.length} connection(s) reported a problem.</>
            )}
            <Skipped items={result.items} onTab={onTab} />
          </Notice>
        )}

      </Card>

      {onTab && (
        <div style={{ textAlign: 'center' }}>
          <button className="link" onClick={() => onTab('import')}>Import from a file</button>
        </div>
      )}
    </div>
  );
}

/**
 * What the sync left out, and where to change it.
 *
 * A bank hands over every account on the login, and most of them are skipped
 * on purpose. Saying nothing about that looks the same as a sync that missed
 * them — and leaves no clue that the choice is yours to make, or where.
 */
function Skipped({ items, onTab }) {
  const names = [...new Set((items ?? []).flatMap((i) => i.skipped_accounts ?? []))];
  if (names.length === 0) return null;

  return (
    <div className="small" style={{ marginTop: 10 }}>
      Skipped {names.length} account{names.length === 1 ? '' : 's'} this bank
      also holds: {names.join(', ')}.{' '}
      <GoTo to="accounts" from="banks" onTab={onTab}>
        Choose which accounts to sync
      </GoTo>
      {' '}— the choice sticks, so a card you switch off stays off.
    </div>
  );
}

/**
 * What the credentials look like, shown only when something has gone wrong.
 *
 * Length and character class, never any part of a value: enough to catch a
 * truncated paste, a swapped pair or a secret from the wrong environment,
 * and useless to anyone reading over your shoulder.
 *
 * It used to sit on the page permanently, which was right while the keys were
 * being set up and clutter once they worked. A diagnostic belongs where the
 * fault is, so it appears with the error and nowhere else.
 */
function Credentials({ shape, environment, check, checking, result }) {
  return (
    <details className="card" style={{ padding: '14px 18px' }}>
      <summary className="small" style={{ cursor: 'pointer' }}>
        Check the Plaid keys for the <strong>{environment}</strong> environment
      </summary>

      <div className="table-wrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr><th>Variable</th><th>Length</th><th>Characters</th><th /></tr>
          </thead>
          <tbody>
            {[['PLAID_CLIENT_ID', shape?.client_id],
              ['PLAID_SECRET', shape?.secret]].map(([name, c]) => (
              <tr key={name}>
                <td className="merchant"><code>{name}</code></td>
                <td>{c?.set ? `${c.length} chars` : 'not set'}</td>
                <td className="muted">
                  {c?.set ? (c.hex_only ? 'hex' : 'mixed') : '—'}
                </td>
                <td>
                  {!c?.set
                    ? <StatusPill state="critical">Missing</StatusPill>
                    : c.had_surrounding_whitespace
                      ? <StatusPill state="warning">Had whitespace</StatusPill>
                      : <StatusPill state="good">Set</StatusPill>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="controls" style={{ marginTop: 12 }}>
        <button className="btn" onClick={check} disabled={checking}>
          {checking ? 'Checking…' : 'Test these against Plaid'}
        </button>
      </div>

      {result && (
        <Notice kind={result.ok ? 'good' : 'error'}>
          {result.ok ? result.message : result.error}
        </Notice>
      )}

    </details>
  );
}
