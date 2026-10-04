import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, Tile, Why,
} from '../components/ui.jsx';
import {
  deleteMortgage, getMortgage, money, monthLabel, pct, previewMortgage,
  saveMortgage,
} from '../api.js';
import { mortgageConfig } from '../charts.js';

/**
 * The mortgage: what it costs a month, when it ends, and how much is interest.
 *
 * Saved, not just calculated: its monthly cost *is* the Mortgage line in the
 * plan's fixed commitments, so the figure here, the plan's sum and the weekly
 * number cannot disagree. Every figure on the page comes from the server —
 * the form and the slider ask it for a preview rather than redoing the sums
 * here, so what you see before saving is what saving gives.
 */

const FREQUENCY_LABELS = {
  monthly: 'Monthly',
  biweekly: 'Every two weeks',
  accelerated_biweekly: 'Every two weeks — accelerated',
  weekly: 'Weekly',
  accelerated_weekly: 'Weekly — accelerated',
};

const PER_PAYMENT = {
  monthly: 'a month', biweekly: 'every two weeks',
  accelerated_biweekly: 'every two weeks', weekly: 'a week',
  accelerated_weekly: 'a week',
};

const EMPTY = { balance: '', rate: '', years: '25', frequency: 'monthly',
                compounding: 'canadian', term_end: '', extra_monthly: 0 };

/** The form, filled from a saved mortgage as it stands this month. */
function formFrom(data) {
  const s = data?.saved;
  const r = data?.result;
  if (!s || !r) return EMPTY;
  // The balance and years as of now, rolled forward from when they were
  // typed — saving again starts the schedule from this month, so the form
  // has to say what is true today, not what was true then.
  const years = (r.without_extra ?? r).years_left;
  return {
    balance: String(r.balance_now),
    rate: String(s.rate),
    years: String(Math.max(Math.round(years * 100) / 100, 1)),
    frequency: s.frequency,
    compounding: s.compounding,
    term_end: s.term_end ?? '',
    extra_monthly: s.extra_monthly ?? 0,
  };
}

function body(form) {
  return {
    balance: Number(form.balance),
    rate: Number(form.rate),
    years: Number(form.years),
    frequency: form.frequency,
    compounding: form.compounding,
    term_end: form.term_end || null,
    extra_monthly: Number(form.extra_monthly) || 0,
  };
}

function complete(form) {
  return Number(form.balance) > 0 && form.rate !== '' && Number(form.years) >= 1;
}

export default function MortgagePanel({ onChanged, onTab }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saved, setSaved] = useState(EMPTY);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function load() {
    setLoadError(null);
    try {
      const d = await getMortgage();
      setData(d);
      const f = formFrom(d);
      setForm(f);
      setSaved(f);
      setPreview(null);
    } catch (e) {
      setLoadError(e);
    }
  }

  useEffect(() => { load(); }, []);

  const dirty = useMemo(
    () => JSON.stringify(body(form)) !== JSON.stringify(body(saved)),
    [form, saved]);

  // Ask the server what the terms on screen give, a moment after typing stops.
  useEffect(() => {
    if (!dirty || !complete(form)) { setPreview(null); return undefined; }
    const id = setTimeout(async () => {
      try {
        setPreview(await previewMortgage(body(form)));
        setError(null);
      } catch (e) {
        setPreview(null);
        setError(e);
      }
    }, 220);
    return () => clearTimeout(id);
  }, [form, dirty]);

  async function run(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
      await onChanged?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data) return <Loading what="your mortgage" />;

  const shown = preview ?? data;
  const r = shown?.result;
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <div className="stack">
      <Card title="Your mortgage"
            hint="Typed once — the payment it works out becomes the Mortgage line in your plan"
            actions={data.saved && !dirty && (
              confirming ? (
                <div className="row" style={{ gap: 8 }}>
                  <button className="btn" disabled={busy}
                          onClick={() => run(deleteMortgage)}>
                    Yes, remove it
                  </button>
                  <button className="btn quiet" onClick={() => setConfirming(false)}>
                    Keep it
                  </button>
                </div>
              ) : (
                <button className="btn quiet" onClick={() => setConfirming(true)}>
                  Remove
                </button>
              ))}>
        <ErrorNote error={error} />
        <form className="stack" style={{ gap: 14 }} onSubmit={(e) => {
          e.preventDefault();
          run(() => saveMortgage(body(form)));
        }}>
          <div className="controls">
            <label htmlFor="mg-balance">Balance owing</label>
            <input id="mg-balance" type="number" min="1" step="any" required
                   inputMode="decimal" value={form.balance} placeholder="500000"
                   onChange={set('balance')} style={{ width: 140 }} />
            <label htmlFor="mg-rate">Interest rate</label>
            <span className="row" style={{ gap: 4 }}>
              <input id="mg-rate" type="number" min="0" max="25" step="any" required
                     inputMode="decimal" value={form.rate} placeholder="4.79"
                     onChange={set('rate')} style={{ width: 90 }} />
              <span className="muted">%</span>
            </span>
            <label htmlFor="mg-years">Years left to pay</label>
            <input id="mg-years" type="number" min="1" max="40" step="any" required
                   inputMode="decimal" value={form.years}
                   onChange={set('years')} style={{ width: 80 }} />
          </div>

          <div className="controls">
            <label htmlFor="mg-frequency">How often you pay</label>
            <select id="mg-frequency" value={form.frequency} onChange={set('frequency')}>
              {Object.entries(FREQUENCY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <label htmlFor="mg-term">Term ends</label>
            <input id="mg-term" type="month" value={form.term_end}
                   onChange={set('term_end')} aria-describedby="mg-term-hint" />
          </div>

          <div className="controls">
            <label>Compounding</label>
            <label className="row small" style={{ gap: 6, color: 'inherit' }}>
              <input type="radio" name="mg-compounding" value="canadian"
                     checked={form.compounding === 'canadian'}
                     onChange={set('compounding')} />
              Canadian — twice a year
            </label>
            <label className="row small" style={{ gap: 6, color: 'inherit' }}>
              <input type="radio" name="mg-compounding" value="monthly"
                     checked={form.compounding === 'monthly'}
                     onChange={set('compounding')} />
              Monthly — US-style
            </label>
          </div>
          <p id="mg-term-hint" className="small muted" style={{ margin: 0 }}>
            The term is how long this rate is fixed (often five years); the
            years left are how long until it is paid off. Canadian fixed-rate
            mortgages compound twice a year by law, which makes the payment a
            little smaller than an American calculator says.
          </p>

          {data.existing && !data.saved && (
            <Notice>
              Your plan already has{' '}
              <strong className="num">{money(data.existing.amount, { cents: true })}</strong>{' '}
              a month for {data.existing.name}. Saving replaces it with what
              these terms work out
              {r ? <> — <strong className="num">
                {money(r.committed_monthly, { cents: true })}</strong></> : ''}
              {' '}— rather than adding a second line.
            </Notice>
          )}

          <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
            <button className="btn primary" type="submit"
                    disabled={busy || !complete(form) || (!dirty && data.saved)}>
              {busy ? 'Saving…' : data.saved ? 'Save changes to the plan' : 'Save to the plan'}
            </button>
            {dirty && data.saved && (
              <button className="btn quiet" type="button"
                      onClick={() => setForm(saved)}>
                Undo changes
              </button>
            )}
            {dirty && (
              <span className="small muted">
                {complete(form) ? 'A preview — nothing is saved until you press Save.'
                  : 'Fill in the balance, rate and years to see it worked out.'}
              </span>
            )}
          </div>
        </form>
      </Card>

      {r && <Results data={shown} r={r} form={form} setForm={setForm}
                     onTab={onTab} />}
    </div>
  );
}

function Results({ data, r, form, setForm, onTab }) {
  const paidOffIn = yearsMonths(r.months_left);
  const interestShare = r.interest_share;

  return (
    <>
      <div className="grid cols-4">
        <Tile label="Out of every month" value={money(r.committed_monthly)}
              note={data.share_of_income != null
                ? `${pct(data.share_of_income)} of your take-home pay`
                : 'Set your take-home on Income to see the share'} />
        <Tile label="Paid off by" value={monthLabel(r.payoff_month)}
              note={`${paidOffIn} from now`} />
        <Tile label="Interest still to pay" value={money(r.total_interest)}
              note={`on ${money(r.total_principal)} owing`} />
        <Tile label="Owing now" value={money(r.balance_now)}
              note={r.as_of && r.balance_now !== Number(form.balance)
                ? `rolled forward from ${monthLabel(r.as_of)}`
                : `${money(r.payment, { cents: true })} ${PER_PAYMENT[r.frequency]}`} />
      </div>

      <Card title="Interest against principal"
            hint="Of everything still to pay, how much clears the debt and how much is the cost of borrowing">
        <div className="split-bar" role="img"
             aria-label={`${pct(interestShare)} interest, ${pct(1 - interestShare)} principal`}>
          <span style={{ width: `${(1 - interestShare) * 100}%`,
                         background: 'var(--series-1)' }} />
          <span style={{ width: `${interestShare * 100}%`,
                         background: 'var(--series-3)' }} />
        </div>
        <div className="legend" style={{ marginTop: 8 }}>
          <span className="item">
            <span className="swatch" style={{ background: 'var(--series-1)' }} />
            Principal — <strong className="num">{money(r.total_principal)}</strong>{' '}
            ({pct(1 - interestShare)})
          </span>
          <span className="item">
            <span className="swatch" style={{ background: 'var(--series-3)' }} />
            Interest — <strong className="num">{money(r.total_interest)}</strong>{' '}
            ({pct(interestShare)})
          </span>
        </div>
        <p className="small muted" style={{ margin: '10px 0 0' }}>
          {money(r.total_paid)} in all.
          {r.next_month?.month && (
            <> Of the payments in {monthLabel(r.next_month.month, { long: true })},{' '}
              <strong className="num">{money(r.next_month.interest, { cents: true })}</strong>{' '}
              is interest and{' '}
              <strong className="num">{money(r.next_month.principal, { cents: true })}</strong>{' '}
              comes off what you owe.</>
          )}
          {r.accelerated && (
            <> Accelerated payments add up to thirteen monthly payments a year
              instead of twelve; the extra one goes entirely to principal.</>
          )}
        </p>
      </Card>

      <ExtraSlider r={r} form={form} setForm={setForm} />

      <Card title="Where each year's payments go"
            hint="Early years are mostly interest; the crossover is when principal takes over">
        <div className="chart">
          <Chart config={mortgageConfig(r.by_year)}
                 ariaLabel={`Year by year, interest and principal paid. `
                   + `${money(r.total_interest)} interest and `
                   + `${money(r.total_principal)} principal in total, `
                   + `paid off by ${monthLabel(r.payoff_month, { long: true })}.`} />
        </div>
        <div className="legend" style={{ marginTop: 6 }}>
          <span className="item">
            <span className="swatch" style={{ background: 'var(--series-1)' }} />
            Principal
          </span>
          <span className="item">
            <span className="swatch" style={{ background: 'var(--series-3)' }} />
            Interest
          </span>
        </div>
        {r.renewal && (
          <p className="assumption" style={{ marginBottom: 0 }}>
            By the end of your term in{' '}
            {monthLabel(r.renewal.month, { long: true })} you&apos;ll owe{' '}
            <strong className="num">{money(r.renewal.balance)}</strong>. Of
            the {money(r.renewal.interest + r.renewal.principal)} you pay
            until then,{' '}
            <strong className="num">{money(r.renewal.interest)}</strong> is
            interest. That balance is what the next rate will apply to.
          </p>
        )}
      </Card>

      <Card title="Shorter or longer"
            hint="The balance owing now, paid off over each length, at this rate">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paid off over</th>
                <th className="r">Payment</th>
                <th className="r">A month</th>
                <th className="r">Total interest</th>
              </tr>
            </thead>
            <tbody>
              {r.alternatives.map((a) => {
                const current = Math.abs(a.years - Number(form.years)) < 0.01;
                return (
                  <tr key={a.years} className={current ? 'current' : ''}>
                    <td>
                      {a.years} years
                      {current && <span className="muted small"> · yours</span>}
                    </td>
                    <td className="r num">
                      {money(a.payment, { cents: true })}{' '}
                      <span className="muted small">{PER_PAYMENT[r.frequency]}</span>
                    </td>
                    <td className="r num">{money(a.monthly_equivalent)}</td>
                    <td className="r num">{money(a.total_interest)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Why id="mortgage.assumption" label="What does this assume?">
          That the rate holds for every year left. It won&apos;t: the term ends,
          the mortgage renews and the rate moves, up or down. The payoff date
          and the interest are what these terms give if nothing changes, which
          makes them useful for comparing choices — paying extra, paying more
          often, a shorter amortization — and not a forecast. The monthly cost
          is what the plan subtracts on{' '}
          <GoTo to="plan" from="mortgage" onTab={onTab} />.
        </Why>
      </Card>
    </>
  );
}

/** Paying extra every month, previewed live through the server. */
function ExtraSlider({ r, form, setForm }) {
  const value = Number(form.extra_monthly) || 0;
  const max = Math.max(Math.ceil(r.monthly_equivalent / 2 / 100) * 100, 500, value);
  const filled = Math.round((value / max) * 100);

  return (
    <Card title="Paying extra"
          hint="On top of the payment, every month — straight off the principal">
      <div className="controls" style={{ alignItems: 'center', gap: 14 }}>
        <label htmlFor="mg-extra" style={{ whiteSpace: 'nowrap' }}>Extra each month</label>
        <input id="mg-extra" className="measure" type="range" min="0" max={max}
               step="25" value={value}
               onChange={(e) => setForm({ ...form, extra_monthly: Number(e.target.value) })}
               style={{
                 flex: '1 1 220px', minWidth: 160,
                 backgroundImage: `linear-gradient(to right, var(--brand) 0 ${
                   filled}%, var(--surface-2) ${filled}% 100%)`,
               }}
               aria-valuetext={`${money(value)} a month`} />
        <strong className="num" style={{ fontSize: 20, minWidth: 80, textAlign: 'right' }}>
          {money(value)}
        </strong>
      </div>
      <p className="small" style={{ margin: '12px 0 0' }}>
        {r.saves
          ? <>Paid off{' '}
              <strong>{yearsMonths(r.saves.months)} sooner</strong>, in{' '}
              {monthLabel(r.payoff_month, { long: true })}, with{' '}
              <strong className="num">{money(r.saves.interest)}</strong> less
              interest. The plan would set aside{' '}
              {money(r.committed_monthly)} a month instead of{' '}
              {money(r.monthly_equivalent)}.</>
          : <span className="muted">Drag it to see what an extra amount each
              month saves. Most lenders allow prepayments up to a yearly limit
              — check yours.</span>}
      </p>
    </Card>
  );
}

function yearsMonths(months) {
  const y = Math.floor(months / 12);
  const m = months % 12;
  const parts = [];
  if (y) parts.push(`${y} year${y === 1 ? '' : 's'}`);
  if (m || !y) parts.push(`${m} month${m === 1 ? '' : 's'}`);
  return parts.join(' ');
}
