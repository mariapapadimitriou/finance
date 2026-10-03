import { useEffect, useState } from 'react';
import {
  Card, Empty, ErrorNote, Loading, Notice, StatusPill, Tile,
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
          <Empty title="No piggy banks yet">
            A monthly budget handles rent well and a holiday badly. The holiday
            costs $3,000 once, so eleven months look like a surplus and the
            twelfth looks like a catastrophe — one that was entirely
            predictable.
          </Empty>

          {/* Not a generic nudge. Travel has no budget line anywhere in the
              app on purpose, so until this bank exists it is the one cost
              nothing at all is paying for. */}
          {suggested && editing !== 'new' && (
            <Notice kind="error">
              <strong>Start with travel.</strong> It is the one category with
              no budget line — a cost that lands in lumps is wrong as a
              monthly figure — so a bank is the only thing that can fund it.
              {suggested.annual_spend > 0 && (
                <> Your last year of travel came to{' '}
                  <strong className="num">{money(suggested.annual_spend)}</strong>
                  {suggested.target > 0 && (
                    <>, about{' '}
                      <strong className="num">
                        {money(suggested.target / 12)}
                      </strong>{' '}
                      a month</>
                  )}.</>
              )}
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn primary" onClick={() => setEditing('new')}>
                  Open a travel bank
                </button>
              </div>
            </Notice>
          )}
          <Card title="What a piggy bank does">
            <p className="muted" style={{ marginTop: 0 }}>
              You name a cost and a target. Two things follow, and the second is
              the one that makes it work:
            </p>
            <ul className="steps">
              <li>
                <strong>Going in.</strong> The target is divided by the months
                available, and that share comes off every month&apos;s budget
                exactly like rent. A holiday in June becomes a bill you are
                already paying.
              </li>
              <li>
                <strong>Coming out.</strong> When you spend on it, you charge
                that transaction to the bank on the Transactions tab. It leaves
                the month it fell in entirely — so June doesn&apos;t look like a
                disaster, because June was never asked to pay for the holiday.
              </li>
            </ul>
            <p className="small muted" style={{ marginBottom: 0 }}>
              Nothing here is typed twice. The monthly figure comes from the
              target and the date; the balance comes from how many months have
              passed and what you have charged to it.
            </p>
          </Card>
        </>
      ) : (
        <>
          <div className="grid cols-3">
            <Tile label="Out of every month" value={money(data.monthly_total)}
                  note={data.income > 0
                    ? `${pct(share)} of your take-home pay`
                    : 'Set your income on the Plan tab to see this as a share'} />
            <Tile label="Held across every bank" value={money(data.balance_total)}
                  note="Collected so far, less what has been charged" />
            <Tile label="Piggy banks" value={String(banks.length)}
                  note={banks.some((b) => b.behind)
                    ? 'One is behind and catching up'
                    : 'None of them behind'} />
          </div>

          {/* No link to the plan from here any more: this is the plan page.
              The figure it refers to is the term in the sum above it. */}
          <Notice>
            These contributions come off the{' '}
            <strong>Yours to spend</strong> figure above before the daily
            number is worked out, which is what &ldquo;deducted equally from
            each month&rdquo; means in practice.
          </Notice>

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
        <button className="btn primary" onClick={() => setEditing('new')}>
          Open a piggy bank
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
                    : ' — the date has arrived'}</>
              : <>{money(b.target)} a year, spread across twelve months</>}
          </p>
          {b.note && <p className="small muted" style={{ margin: '4px 0 0' }}>{b.note}</p>}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="big num">{money(b.monthly)}</div>
          <div className="per">
            a month{b.catch_up > 0 && <>, incl. {money(b.catch_up)} catching up</>}
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
          <span className="muted">In it now </span>
          <strong className="num">{money(b.balance, { cents: true })}</strong>
        </span>
        <span className="muted num">
          {money(b.accrued)} collected · {money(b.charged)} charged to it
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
            Closing {b.name} puts the {money(b.charged)} charged to it back into
            the months it was spent in, so those months will read higher than
            they do now. The money was always spent — this only changes which
            month it counts against.
          </Notice>
        </div>
      )}

      {b.behind && (
        <div className="assumption" style={{ marginBottom: 0 }}>
          You spent {money(b.behind_by)} more out of this than it had
          collected, so it is paying itself back: the contribution is{' '}
          <strong className="num">{money(b.monthly)}</strong> a month instead
          of {money(b.base_monthly)} until it is whole, which at this rate is{' '}
          {b.caught_up_by ? monthLabel(b.caught_up_by, { long: true }) : 'soon'}.
          That is the trip coming off the months ahead rather than out of the
          month you took it.
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
    <Card title={bank ? `Edit ${bank.name}` : 'Open a piggy bank'}>
      <ErrorNote error={error} />
      <form className="stack" onSubmit={save} style={{ gap: 16 }}>
        <div className="controls">
          <label htmlFor="pb-name">What it is for</label>
          <input id="pb-name" type="text" value={name} required
                 placeholder="Vacation, car, Christmas…"
                 onChange={(e) => setName(e.target.value)}
                 style={{ flex: '1 1 200px' }} />
        </div>

        <div className="controls">
          <label htmlFor="pb-target">How much you need</label>
          <input id="pb-target" type="number" min="1" step="any" required
                 inputMode="decimal" value={target} style={{ width: 130 }}
                 onChange={(e) => setTarget(e.target.value)} />
          <label htmlFor="pb-opening">Already set aside</label>
          <input id="pb-opening" type="number" min="0" step="any" placeholder="0"
                 inputMode="decimal" value={opening} style={{ width: 130 }}
                 onChange={(e) => setOpening(e.target.value)} />
        </div>

        <div>
          <div className="controls">
            <label>When you need it</label>
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
              By a date
            </label>
            {cadence === 'once' && (
              <input type="date" value={date} required aria-label="Needed by"
                     onChange={(e) => setDate(e.target.value)} />
            )}
          </div>
          <p className="small muted" style={{ margin: '8px 0 0' }}>
            {cadence === 'annual'
              ? 'A cost that comes round again — car maintenance, insurance, '
                + 'Christmas. It collects twelve months a year, forever, and '
                + 'refills after you spend it.'
              : 'A cost with a date — a trip, a wedding. It stops collecting '
                + 'once the date arrives.'}
          </p>
        </div>

        <div className="controls">
          <label htmlFor="pb-note">Note</label>
          <input id="pb-note" type="text" value={note}
                 placeholder="Optional — anything worth remembering"
                 onChange={(e) => setNote(e.target.value)}
                 style={{ flex: '1 1 200px' }} />
        </div>

        {monthly > 0 && (
          <Notice>
            <strong>{money(monthly)} a month.</strong>{' '}
            {money(needed)} still to collect
            {cadence === 'annual'
              ? ', over twelve months'
              : ` over ${months} month${months === 1 ? '' : 's'}`}
            . That comes off what you have to spend each month, starting now.
          </Notice>
        )}

        <div className="row">
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : bank ? 'Save changes' : 'Open it'}
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
