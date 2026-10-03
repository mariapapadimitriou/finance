import { useEffect, useState } from 'react';
import {
  Card, ErrorNote, Loading, Notice, StatusPill, Tile,
} from '../components/ui.jsx';
import {
  addBank, dateLabel, deleteBank, getBanks, money, monthLabel, pct, updateBank,
} from '../api.js';

/**
 * Piggy banks: the costs that don't arrive monthly, budgeted monthly anyway.
 *
 * Two numbers matter per bank and they answer different questions. The monthly
 * contribution is what this bank costs you every month — it comes off the
 * Plan's leftover like rent. The balance is what is in it now, which is what
 * you can actually spend. Showing one without the other is how you end up
 * either surprised by a small daily allowance or surprised by an empty fund.
 */
export default function PiggyPanel({ version = 0 }) {
  const [data, setData] = useState(null);
  // A failed load has nothing to show and replaces the panel; anything that
  // fails while acting must leave the page and any half-filled form standing.
  const [loadError, setLoadError] = useState(null);
  const [editing, setEditing] = useState(null);     // bank id, or 'new'

  async function load() {
    setLoadError(null);
    try {
      setData(await getBanks());
    } catch (e) {
      setLoadError(e);
    }
  }

  // `version` changes on an import, which changes what has been charged.
  useEffect(() => { load(); }, [version]);

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data) return <Loading what="piggy banks" />;

  const banks = data.banks ?? [];
  const share = data.income > 0 ? data.monthly_total / data.income : 0;
  // The first bank the app wants you to have: travel, because the budget
  // deliberately has no line for it. Null once any bank exists.
  const suggested = data.suggested;

  return (
    <div className="stack">
      {banks.length === 0 ? (
        <>
          <Card title="Piggy banks">
            <p className="muted" style={{ margin: 0 }}>
              Save a little each month for costs that come once a year — trips,
              insurance, gifts. Spending you pay from a piggy bank won&apos;t
              count against that month.
            </p>
            {suggested && editing !== 'new' && (
              <div className="row" style={{ marginTop: 14, gap: 12, flexWrap: 'wrap' }}>
                <button className="btn primary" onClick={() => setEditing('new')}>
                  Start a travel fund
                </button>
                {suggested.target > 0 && (
                  <span className="small muted">
                    Last year&apos;s travel: {money(suggested.annual_spend)}
                    {' '}(~{money(suggested.target / 12)}/month)
                  </span>
                )}
              </div>
            )}
          </Card>
        </>
      ) : (
        <>
          <div className="section-head"><h2>Piggy banks</h2></div>
          <div className="grid cols-3">
            <Tile label="Saving per month" value={money(data.monthly_total)}
                  note={data.income > 0 ? `${pct(share)} of your pay` : undefined} />
            <Tile label="Saved so far" value={money(data.balance_total)} />
            <Tile label="Piggy banks" value={String(banks.length)}
                  note={banks.some((b) => b.behind) ? 'Some catching up' : undefined} />
          </div>

          <div className="stack">
            {banks.map((b) => (
              <Bank key={b.id} bank={b}
                    editing={editing === b.id}
                    onEdit={() => setEditing(editing === b.id ? null : b.id)}
                    onDone={async () => { setEditing(null); await load(); }} />
            ))}
          </div>
        </>
      )}

      {editing === 'new' ? (
        <BankForm suggest={suggested} onCancel={() => setEditing(null)}
                  onSaved={async () => { setEditing(null); await load(); }} />
      ) : (
        <button className="btn" onClick={() => setEditing('new')}>
          + New piggy bank
        </button>
      )}
    </div>
  );
}

function Bank({ bank: b, editing, onEdit, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(false);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteBank(b.id);
      await onDone();
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  if (editing) {
    return <BankForm bank={b} onCancel={onEdit} onSaved={onDone} />;
  }

  const state = b.behind ? 'warning' : b.funded_share >= 1 ? 'good' : 'warning';
  const label = b.behind ? 'Catching up'
    : b.funded_share >= 1 ? 'Fully funded' : 'Filling';

  return (
    <section className="card">
      <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="row" style={{ gap: 10 }}>
            <h3 style={{ margin: 0 }}>{b.name}</h3>
            <StatusPill state={state}>{label}</StatusPill>
          </div>
          <p className="small muted" style={{ margin: '6px 0 0' }}>
            {b.cadence === 'once'
              ? <>{money(b.target)} by {dateLabel(b.target_date)}
                  {b.months_left > 0
                    ? ` — ${b.months_left} month${b.months_left === 1 ? '' : 's'} to go`
                    : ' — due now'}</>
              : <>{money(b.target)} a year</>}
          </p>
          {b.note && <p className="small muted" style={{ margin: '4px 0 0' }}>{b.note}</p>}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="big num">{money(b.monthly)}</div>
          <div className="per">
            a month{b.catch_up > 0 && <> (incl. {money(b.catch_up)} catch-up)</>}
          </div>
        </div>
      </div>

      <div className="track" style={{
        background: 'var(--surface-2)', borderRadius: 4, height: 8,
        overflow: 'hidden', marginTop: 16,
      }}>
        <div style={{
          width: `${Math.min(Math.max(b.funded_share, 0), 1) * 100}%`,
          height: '100%', borderRadius: '0 4px 4px 0',
          background: `var(--${state === 'good' ? 'good' : state})`,
        }} />
      </div>

      <div className="row small" style={{ marginTop: 10, gap: 18, flexWrap: 'wrap' }}>
        <span>
          <span className="muted">Saved </span>
          <strong className="num">{money(b.balance, { cents: true })}</strong>
        </span>
        <span className="muted num">
          {money(b.accrued)} in · {money(b.charged)} spent
        </span>
        <span className="spacer" />
        <button className="btn quiet" onClick={onEdit}>Edit</button>
        {confirming ? (
          <>
            <button className="btn" onClick={remove} disabled={busy}>
              {busy ? 'Closing…' : 'Yes, close it'}
            </button>
            <button className="btn quiet" onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </>
        ) : (
          <button className="btn quiet" onClick={() => setConfirming(true)}>
            Close
          </button>
        )}
      </div>

      {confirming && (
        <div style={{ marginTop: 12 }}>
          <Notice>
            {b.charged > 0
              ? `The ${money(b.charged)} spent from it will count against the months it was spent in.`
              : 'Close this piggy bank?'}
          </Notice>
        </div>
      )}

      {b.behind && (
        <div className="assumption" style={{ marginBottom: 0 }}>
          {money(b.behind_by)} behind. Saving{' '}
          <strong className="num">{money(b.monthly)}</strong> a month (normally{' '}
          {money(b.base_monthly)}) until{' '}
          {b.caught_up_by ? monthLabel(b.caught_up_by, { long: true }) : 'it catches up'}.
        </div>
      )}
    </section>
  );
}

/** Opening or editing a bank. The monthly figure is shown, never typed. */
function BankForm({ bank, suggest, onCancel, onSaved }) {
  // `suggest` only arrives for the very first bank, and only as a starting
  // point: both fields stay editable, because a target she did not choose is
  // a monthly deduction she did not agree to.
  const [name, setName] = useState(bank?.name ?? suggest?.name ?? '');
  const [target, setTarget] = useState(bank?.target ?? suggest?.target ?? '');
  const [cadence, setCadence] = useState(bank?.cadence ?? 'annual');
  const [date, setDate] = useState(bank?.target_date ?? '');
  const [opening, setOpening] = useState(bank?.opening ?? '');
  const [note, setNote] = useState(bank?.note ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // The same arithmetic the server does, so the figure you are agreeing to is
  // on screen before you press the button.
  const needed = Math.max(Number(target || 0) - Number(opening || 0), 0);
  const months = cadence === 'annual' ? 12 : monthsUntil(date);
  const monthly = months > 0 ? needed / months : 0;

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name,
      target: Number(target || 0),
      cadence,
      target_date: cadence === 'once' ? date : null,
      opening: Number(opening || 0),
      note,
    };
    try {
      if (bank) await updateBank(bank.id, body);
      else await addBank(body);
      await onSaved();
    } catch (e2) {
      setError(e2);
      setBusy(false);
    }
  }

  return (
    <Card title={bank ? `Edit ${bank.name}` : 'New piggy bank'}>
      <ErrorNote error={error} />
      <form className="stack" onSubmit={save} style={{ gap: 16 }}>
        <div className="controls">
          <label htmlFor="pb-name">Name</label>
          <input id="pb-name" type="text" value={name} required
                 placeholder="Vacation, car, Christmas…"
                 onChange={(e) => setName(e.target.value)}
                 style={{ flex: '1 1 200px' }} />
        </div>

        <div className="controls">
          <label htmlFor="pb-target">Goal</label>
          <input id="pb-target" type="number" min="1" step="any" required
                 inputMode="decimal" value={target} style={{ width: 130 }}
                 onChange={(e) => setTarget(e.target.value)} />
          <label htmlFor="pb-opening">Already saved</label>
          <input id="pb-opening" type="number" min="0" step="any" placeholder="0"
                 inputMode="decimal" value={opening} style={{ width: 130 }}
                 onChange={(e) => setOpening(e.target.value)} />
        </div>

        <div>
          <div className="controls">
            <label>Repeats</label>
            <label className="row small" style={{ gap: 6, color: 'inherit' }}>
              <input type="radio" name="cadence" value="annual"
                     checked={cadence === 'annual'}
                     onChange={() => setCadence('annual')} />
              Every year
            </label>
            <label className="row small" style={{ gap: 6, color: 'inherit' }}>
              <input type="radio" name="cadence" value="once"
                     checked={cadence === 'once'}
                     onChange={() => setCadence('once')} />
              Once, by
            </label>
            {cadence === 'once' && (
              <input type="date" value={date} required aria-label="Needed by"
                     onChange={(e) => setDate(e.target.value)} />
            )}
          </div>
        </div>

        <div className="controls">
          <label htmlFor="pb-note">Note</label>
          <input id="pb-note" type="text" value={note}
                 placeholder="Optional"
                 onChange={(e) => setNote(e.target.value)}
                 style={{ flex: '1 1 200px' }} />
        </div>

        {monthly > 0 && (
          <Notice>
            <strong>{money(monthly)} a month</strong> comes out of your
            spending money{cadence === 'once'
              ? ` for ${months} month${months === 1 ? '' : 's'}`
              : ''}.
          </Notice>
        )}

        <div className="row">
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : bank ? 'Save' : 'Create'}
          </button>
          <button className="btn quiet" type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>
    </Card>
  );
}

/** Whole calendar months from this month to the target's, both counted. */
function monthsUntil(iso) {
  if (!iso) return 0;
  const now = new Date();
  const [y, m] = iso.split('-').map(Number);
  if (!y || !m) return 0;
  return Math.max((y * 12 + m) - (now.getFullYear() * 12 + now.getMonth() + 1) + 1, 1);
}
