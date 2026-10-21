import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { createLinkToken, getAuthStatus, getHome, money, syncPlaid } from '../api.js';
import { loadPlaidScript } from '../plaid.js';
import { Alert, DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import './home.css';

/**
 * Home, stripped down (2026-10-21).
 *
 * The app lands here. It says hello, names the day, shows the one thing
 * that may need her — a bank that wants her to sign in again (THL-120 C-02
 * to C-05) — says how many transactions need a look (THL-123), and opens
 * Transactions. The safe-to-spend card, the path, wins, the calendar strip,
 * cards, budgets and debts that used to live here went with Save and Wins;
 * Cash flow has the numbers.
 */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
export const MONTH_NAMES = MONTHS;
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function parts(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m, d, weekday: DAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] };
}

/** "October" from "2026-10" or "2026-10-09". */
export const monthName = (iso) => MONTHS[parts(`${iso.slice(0, 7)}-01`).m - 1];
/** "Oct 12". */
export const shortDate = (iso) => { const p = parts(iso); return `${MONTHS[p.m - 1].slice(0, 3)} ${p.d}`; };
/** "Friday, October 16". */
export const longDate = (iso) => { const p = parts(iso); return `${p.weekday}, ${MONTHS[p.m - 1]} ${p.d}`; };

/** An amount as shown: never signed, cents where the decisions ask for them. */
export const shown = (n, cents = false) => money(Math.abs(n), { cents });

/** "today", a weekday within the week, else "Oct 12". */
export function whenWords(iso, today) {
  if (!iso) return 'a while ago';
  const day = iso.slice(0, 10);
  if (!today || day === today) return 'today';
  const days = Math.round((Date.parse(today) - Date.parse(day)) / 86400000);
  return days > 0 && days < 7 ? parts(day).weekday : shortDate(day);
}

/** "Good morning" by the hour, the way H-01 greets her. */
export function greeting(hour = new Date().getHours()) {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

/** The one alert Home shows: a bank connection that needs her (C3 order). */
export function homeAlert(connections = [], back = null, today = null) {
  const c = connections[0];
  if (c?.state === 'needs_sign_in') {
    const what = c.cards_only ? 'Card purchases' : 'Transactions';
    return { tone: 'caution', action: 'Reconnect', connection: c,
             text: `${c.institution} needs you to sign in again. ${what} since ${whenWords(c.last_synced, today)} aren’t counted yet.` };
  }
  if (c?.state === 'disconnected') {
    return { tone: 'caution', action: 'See accounts', connection: c,
             text: `${c.institution} is no longer connected, so its transactions aren’t coming in.` };
  }
  if (c?.state === 'bank_down') {
    return { tone: 'info', action: 'Details', connection: c,
             text: `${c.institution} isn’t responding right now. We’ll keep trying; there’s nothing you need to do.` };
  }
  if (back) return { tone: 'positive', text: `${back} is back up to date.` };
  return null;
}

export default function HomePanel({ onTab, onChanged, version }) {
  const [home, setHome] = useState(null);
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const [reconnect, setReconnect] = useState(null);
  const [back, setBack] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return Promise.all([getHome(), getAuthStatus().catch(() => ({}))])
      .then(([h, a]) => { setHome(h); setUser(a.user ?? null); })
      .catch(setError);
  }, []);
  // `version` moves after every import and sync, so the count follows them.
  useEffect(() => { load(); }, [load, version]);

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!home) return <div className="pk hm-page"><p className="pk-muted" role="status">Loading Home…</p></div>;

  const alert = homeAlert(home.connections, back, home.today);
  const act = () => {
    if (alert?.action === 'Reconnect') setReconnect(alert.connection);
    else onTab?.('accounts');
  };
  const name = user?.first_name || user?.username || '';
  return (
    <div className="pk hm-page">
      <header className="hm-head">
        <p className="pk-overline">{longDate(home.today)}</p>
        <h1 className="pk-h1">{name ? `${greeting()}, ${name}` : greeting()}</h1>
      </header>

      {alert && (
        <Alert tone={alert.tone ?? 'info'} action={alert.action} onAction={alert.action ? act : undefined}>
          {alert.text}
        </Alert>
      )}

      {home.review_count > 0 && (
        <NeedsALook count={home.review_count} onReview={() => onTab?.('review')} />
      )}

      <section className="hm-card" aria-labelledby="hm-tx-title">
        <h2 className="pk-h3" id="hm-tx-title">{`${monthName(home.month)} so far`}</h2>
        <p className="pk-muted">Every transaction, what needs a look, and your month in pictures are on Cash flow.</p>
        <button type="button" className="hm-link" onClick={() => onTab?.('transactions')}>
          Transactions <PIcon name="chevronRight" size={14} />
        </button>
      </section>

      {reconnect && (
        <ReconnectPanel connection={reconnect} onClose={() => setReconnect(null)}
                        onDone={() => { setBack(reconnect.institution); setReconnect(null); load(); onChanged?.(); }} />
      )}
    </div>
  );
}

/** "N transactions need a look" (THL-123), opening To review. Hidden at 0. */
export function NeedsALook({ count, onReview }) {
  return (
    <section className="hm-card" aria-labelledby="hm-look-title">
      <h2 className="pk-h3" id="hm-look-title">
        {count === 1 ? '1 transaction needs a look' : `${count} transactions need a look`}
      </h2>
      <p className="pk-muted">We weren’t sure how to sort these. Sorting them keeps your numbers right.</p>
      <button type="button" className="hm-link" onClick={onReview}>
        Review <PIcon name="chevronRight" size={14} />
      </button>
    </section>
  );
}

/** C-04: sign in to the bank again, through Plaid in update mode. */
export function ReconnectPanel({ connection, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inst = connection.institution;
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const [Plaid, { link_token: token }] = await Promise.all([
        loadPlaidScript(), createLinkToken(connection.item_id)]);
      Plaid.create({
        token,
        // Update mode: the connection carries on, so there's nothing to
        // exchange. Sync straight away so Home is current again.
        onSuccess: async () => {
          try { await syncPlaid(true); } catch { /* the next sync catches up */ }
          setBusy(false);
          onDone?.();
        },
        onExit: (err) => {
          setBusy(false);
          if (err) setError(err.display_message || err.error_message || 'Signing in didn’t finish. You can try again.');
        },
      }).open();
    } catch (err) {
      setBusy(false);
      setError(err.message);
    }
  };
  return (
    <DetailPanel label={`Sign in to ${inst} again`} overline="Reconnect" onClose={onClose}>
      <h1 className="pk-h2">{`Sign in to ${inst} again`}</h1>
      <p className="pk-muted">
        Banks ask you to sign in again every so often. It’s routine, and nothing is wrong with
        your account.
      </p>
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton onClick={start} disabled={busy}>{busy ? 'Opening…' : `Continue to ${inst}`}</PButton>
      <PButton variant="secondary" onClick={onClose}>Not now</PButton>
      <p className="pk-label pk-muted">You’ll sign in through Plaid. Pearl stays read-only.</p>
    </DetailPanel>
  );
}
