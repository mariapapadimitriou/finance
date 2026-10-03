import { useEffect, useState } from 'react';
import {
  Card, Empty, ErrorNote, GoTo, Loading, Notice, StatusPill, Tile,
} from '../components/ui.jsx';
import {
  addBank, dateLabel, deleteBank, getBanks, money, monthLabel, pct, updateBank,
} from '../api.js';

/**
 * Piggy banks: big spending, kept out of the weekly allowance.
 *
 * The weekly number is for habits. A trip is not a habit, so a bank pays for
 * it instead: you say what it pays for (Travel, say) and every charge in
 * those categories comes out of the bank by itself.
 *
 * Two numbers matter per bank and they answer different questions. The monthly
 * contribution is what this bank costs you every month — it comes off the
 * Plan's leftover like rent. What is available is what you can spend from it
 * this year: the whole target, from the day it opens, less what it has paid.
 */
export default function PiggyPanel({ onTab, version = 0 }) {
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

          {/* Not a generic nudge: travel is the big spending almost
              everyone has, and until a bank pays for it every trip lands on
              the week it was booked in. */}
          {suggested && editing !== 'new' && (
            <Notice kind="error">
              <strong>Start with travel.</strong> Trips arrive in lumps, not
              habits, so they don&apos;t belong in a weekly allowance — until
              a bank pays for them, the week you book a flight reads as a
              disaster.
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
              You name your big spending and how much it gets a year. Two
              things follow:
            </p>
            <ul className="steps">
              <li>
                <strong>The money is there from day one.</strong> Open an
                $8,000 travel bank and you can spend $8,000 on travel today.
                A twelfth of it comes off every month, like rent — and after
                the first year it only takes back what you actually spent.
              </li>
              <li>
                <strong>It pays by itself.</strong> Choose what it pays for,
                and every charge in those categories comes out of the bank
                instead of your week. A one-off in any other category can be
                charged to it in{' '}
                <GoTo to="transactions" from="plan" onTab={onTab} />.
              </li>
            </ul>
          </Card>
        </>
      ) : (
        <>
          <div className="grid cols-3">
            <Tile label="Out of every month" value={money(data.monthly_total)}
                  note={data.income > 0
                    ? `${pct(share)} of your take-home pay`
                    : 'Set your take-home above to see this as a share'} />
            <Tile label="Available across every bank"
                  value={money(data.balance_total)}
                  note="What they can still pay this year" />
            <Tile label="Piggy banks" value={String(banks.length)}
                  note={overCount(banks)} />
          </div>

          {/* No link to the plan from here any more: this is the plan page.
              The figure it refers to is the term in the sum above it. */}
          <Notice>
            These contributions come off the{' '}
            <strong>Yours to spend</strong> figure above before the weekly
            number is worked out. In return, everything a bank pays for comes
            out of the bank, never out of your week.
          </Notice>

          <div className="stack">
            {banks.map((b) => (
              <Bank key={b.id} bank={b} banks={banks}
                    all={data.spend_categories ?? []}
                    editing={editing === b.id}
                    onEdit={() => setEditing(editing === b.id ? null : b.id)}
                    onDone={async () => { setEditing(null); await load(); }} />
            ))}
          </div>
        </>
      )}

      {editing === 'new' ? (
        <BankForm suggest={suggested} banks={banks}
                  all={data.spend_categories ?? []}
                  onCancel={() => setEditing(null)}
                  onSaved={async () => { setEditing(null); await load(); }} />
      ) : (
        <button className="btn primary" onClick={() => setEditing('new')}>
          Open a piggy bank
        </button>
      )}
    </div>
  );
}

function Bank({ bank: b, banks, all, editing, onEdit, onDone }) {
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
    return <BankForm bank={b} banks={banks} all={all}
                     onCancel={onEdit} onSaved={onDone} />;
  }

  const dated = b.cadence === 'once';
  const state = b.over ? 'warning' : 'good';
  const label = b.over ? 'Over this year'
    : dated && b.complete ? 'Done' : 'Ready';
  const share = b.target > 0 ? Math.min(Math.max(b.available / b.target, 0), 1) : 0;
  const cats = b.categories ?? [];

  return (
    <section className="card">
      <ErrorNote error={error} />
      <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="row" style={{ gap: 10 }}>
            <h3 style={{ margin: 0 }}>{b.name}</h3>
            <StatusPill state={state}>{label}</StatusPill>
          </div>
          <p className="small muted" style={{ margin: '6px 0 0' }}>
            {dated
              ? <>{money(b.target)} by {dateLabel(b.target_date)}</>
              : <>{money(b.target)} a year ·{' '}
                  {monthLabel(b.year_start)} – {monthLabel(b.year_end)}</>}
          </p>
          <p className="small" style={{ margin: '4px 0 0' }}>
            {cats.length > 0
              ? <>Pays for <strong>{cats.join(', ')}</strong> by itself</>
              : <span className="muted">
                  Pays for nothing by itself — charge things to it from
                  Transactions, or edit it to choose categories
                </span>}
          </p>
          {b.note && <p className="small muted" style={{ margin: '4px 0 0' }}>{b.note}</p>}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="big num">{money(b.monthly)}</div>
          <div className="per">a month — {basisText(b)}</div>
        </div>
      </div>

      <div className="track" style={{
        background: 'var(--surface-2)', borderRadius: 4, height: 8,
        overflow: 'hidden', marginTop: 16,
      }}>
        <div style={{
          width: `${share * 100}%`,
          height: '100%', borderRadius: '0 4px 4px 0',
          background: `var(--${state})`,
        }} />
      </div>

      <div className="row small" style={{ marginTop: 10, gap: 18, flexWrap: 'wrap' }}>
        <span>
          <span className="muted">Available {dated ? '' : 'this year '}</span>
          <strong className="num">{money(b.available, { cents: true })}</strong>
          <span className="muted"> of {money(b.target)}</span>
        </span>
        <span className="muted num">
          {money(b.spent_this_year)} spent {dated ? 'from it' : 'this year'}
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
            Closing {b.name} puts the {money(b.charged)} it paid back into
            the weeks it was spent in, so those will read higher than they
            do now
            {cats.length > 0 && <>, and {cats.join(' and ')} go back to
              being everyday spending</>}
            . The money was always spent — this only changes what it
            counts against.
          </Notice>
        </div>
      )}

      {b.over && (
        <div className="assumption" style={{ marginBottom: 0 }}>
          It has paid {money(b.spent_this_year)}{dated ? '' : ' this year'},{' '}
          {money(b.behind_by)} more than its {money(b.target)}. That is
          allowed — sometimes the trip costs what it costs — and it changes
          nothing {dated ? 'now' : 'this year'}.{' '}
          {dated
            ? <>The extra is repaid over the twelve months after{' '}
                {dateLabel(b.target_date)}.</>
            : <>From {monthLabel(nextMonth(b.year_end), { long: true })} it
                takes{' '}
                <strong className="num">{money(b.spent_this_year / 12)}</strong>{' '}
                a month to repay what it spent.</>}
        </div>
      )}
    </section>
  );
}

/** Why this month's contribution is what it is, in a few words. */
function basisText(b) {
  switch (b.basis) {
    case 'first_year': return 'first year';
    case 'repaying': return b.cadence === 'once'
      ? 'repaying the overspend'
      : `repaying last year's ${money(b.spent_last_year)}`;
    case 'full': return 'nothing spent last year, so nothing to repay';
    case 'dated': return 'until the date';
    case 'done': return 'finished';
    default: return '';
  }
}

function overCount(banks) {
  const n = banks.filter((b) => b.over).length;
  if (n === 0) return 'None of them over this year';
  return n === 1 ? 'One is over this year' : `${n} are over this year`;
}

function nextMonth(ym) {
  const [y, m] = (ym || '').split('-').map(Number);
  if (!y || !m) return ym;
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
}

/** Opening or editing a bank. The monthly figure is shown, never typed. */
function BankForm({ bank, suggest, banks = [], all = [], onCancel, onSaved }) {
  // `suggest` only arrives for the very first bank, and only as a starting
  // point: both fields stay editable, because a target she did not choose is
  // a monthly deduction she did not agree to.
  const [name, setName] = useState(bank?.name ?? suggest?.name ?? '');
  const [target, setTarget] = useState(bank?.target ?? suggest?.target ?? '');
  const [cadence, setCadence] = useState(bank?.cadence ?? 'annual');
  const [date, setDate] = useState(bank?.target_date ?? '');
  const [opening, setOpening] = useState(bank?.opening ?? '');
  const [note, setNote] = useState(bank?.note ?? '');
  const [cats, setCats] = useState(bank?.categories ?? suggest?.categories ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // The same arithmetic the server does, so the figure you are agreeing to is
  // on screen before you press the button.
  const needed = Math.max(Number(target || 0) - Number(opening || 0), 0);
  const months = cadence === 'annual' ? 12 : monthsUntil(date);
  const monthly = months > 0 ? needed / months : 0;

  // Category → the other bank that already pays for it. A category belongs to
  // one bank, so those are shown but can't be ticked.
  const taken = {};
  for (const other of banks) {
    if (bank && other.id === bank.id) continue;
    for (const c of other.categories ?? []) taken[c] = other.name;
  }
  const toggle = (c) => setCats(cats.includes(c)
    ? cats.filter((x) => x !== c) : [...cats, c]);

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
      categories: cats,
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
              ? 'Spending that comes round every year — trips, Christmas, car '
                + 'upkeep. The whole amount is there from day one, and each '
                + 'year after the first it takes back only what you spent.'
              : 'A cost with a date — a wedding. The whole amount is there '
                + 'now, paid in month by month until the date.'}
          </p>
        </div>

        <fieldset className="pays-for">
          <legend>What it pays for</legend>
          <p className="small muted" style={{ margin: '0 0 8px' }}>
            Every charge in these categories, from this month on, comes out
            of this bank instead of your week. Leave them all unticked to
            charge things to it by hand.
          </p>
          <div className="checks">
            {all.map((c) => (
              <label key={c} className="row small"
                     style={{ gap: 6, color: taken[c] ? 'var(--muted)' : 'inherit' }}>
                <input type="checkbox" checked={cats.includes(c)}
                       disabled={Boolean(taken[c])}
                       onChange={() => toggle(c)} />
                {c}{taken[c] && <span className="muted"> · {taken[c]}</span>}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="controls">
          <label htmlFor="pb-note">Note</label>
          <input id="pb-note" type="text" value={note}
                 placeholder="Optional — anything worth remembering"
                 onChange={(e) => setNote(e.target.value)}
                 style={{ flex: '1 1 200px' }} />
        </div>

        {monthly > 0 && (
          <Notice>
            <strong>
              {money(Number(target || 0))} to spend from{' '}
              {bank ? 'the start of each year' : 'today'}.
            </strong>{' '}
            {cadence === 'annual'
              ? <>In its first year it takes {money(monthly)} a month to pay
                  that in; after that, a twelfth of whatever it spent the
                  year before.</>
              : <>It takes {money(monthly)} a month for {months} month
                  {months === 1 ? '' : 's'} to pay that in.</>}
            {' '}That comes off what you have to spend each month.
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
