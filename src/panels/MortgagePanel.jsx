import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, Tile, } from '../components/ui.jsx';
import {
  compareMortgage, deleteMortgage, getMortgage, money, monthLabel, pct,
  previewMortgage, saveMortgage,
} from '../api.js';
import { investOrPayDownConfig, mortgageConfig } from '../charts.js';

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

const EMPTY = { balance: '', rate: '', years: '25', months: '0', frequency: 'monthly',
                compounding: 'canadian', term_years: '', term_months: '',
                extra_monthly: 0, actual_payment: '', original: '',
                shared: false, share_mode: 'percent', share_value: '50',
                as_of: '', as_of_balance: '', as_of_months: '' };

/** Left to pay, in months: what the two boxes say together. */
function totalMonths(form) {
  return (Math.trunc(Number(form.years)) || 0) * 12 + (Math.trunc(Number(form.months)) || 0);
}

/** Decimal years, as stored, back into whole years and months. */
function splitYears(years) {
  let y = Math.floor(Number(years) || 0);
  let m = Math.round(((Number(years) || 0) - y) * 12);
  if (m === 12) { y += 1; m = 0; }
  return { y, m };
}

/**
 * The form, filled with exactly what was typed.
 *
 * Never with what the arithmetic made of it: the payoff time is an output,
 * and with accelerated payments or an extra it is shorter than the years
 * typed. Putting it back in the box fed it in again as the amortization,
 * which raised the payment and shortened the loan on every save.
 */
function formFrom(data) {
  const s = data?.saved;
  const r = data?.result;
  if (!s || !r) return EMPTY;
  return {
    balance: String(s.balance),
    rate: String(s.rate),
    years: String(splitYears(s.years).y),
    months: String(splitYears(s.years).m),
    // The month those two were true in. Re-saved unchanged, they keep it,
    // so editing the rate doesn't restart a schedule already under way.
    as_of: s.as_of ?? '',
    as_of_balance: String(s.balance),
    as_of_months: String(Math.round(Number(s.years) * 12)),
    frequency: s.frequency,
    compounding: s.compounding,
    // The term is typed as what's left of it, the way a statement says it,
    // and stored as the month it ends — so it counts down by itself.
    ...termLeft(s.term_end),
    actual_payment: s.actual_payment ? String(s.actual_payment) : '',
    original: s.original ? String(s.original) : '',
    extra_monthly: s.extra_monthly ?? 0,
    shared: !(s.share_mode === 'percent' && Number(s.share_value) >= 100),
    share_mode: s.share_mode ?? 'percent',
    share_value: s.share_mode === 'percent' && Number(s.share_value) >= 100
      ? '50' : String(s.share_value ?? 50),
  };
}

function body(form) {
  return {
    balance: Number(form.balance),
    rate: Number(form.rate),
    // Sent as years, at full precision: the server rounds years × 12 back
    // to exactly the months typed.
    years: totalMonths(form) / 12,
    frequency: form.frequency,
    compounding: form.compounding,
    term_end: termEnd(form),
    actual_payment: Number(form.actual_payment) || null,
    original: Number(form.original) || null,
    extra_monthly: Number(form.extra_monthly) || 0,
    // Not shared is simply 100% yours.
    share_mode: form.shared ? form.share_mode : 'percent',
    share_value: form.shared ? Number(form.share_value) || 0 : 100,
    // A new balance or years starts again from this month; the server
    // supplies it when none is sent.
    ...(form.as_of
        && Number(form.balance) === Number(form.as_of_balance)
        && totalMonths(form) === Number(form.as_of_months)
      ? { as_of: form.as_of } : {}),
  };
}

/** "4 years 2 months" left → the month the term ends; nothing typed → none. */
function termEnd(form) {
  const total = (Math.trunc(Number(form.term_years)) || 0) * 12
    + (Math.trunc(Number(form.term_months)) || 0);
  if (total <= 0) return null;
  const now = new Date();
  const index = now.getFullYear() * 12 + now.getMonth() + total;
  return `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, '0')}`;
}

/** The month a term ends → how much of it is left, as the two boxes. */
function termLeft(end) {
  if (!end) return { term_years: '', term_months: '' };
  const [y, m] = end.split('-').map(Number);
  const now = new Date();
  const left = Math.max((y * 12 + m - 1) - (now.getFullYear() * 12 + now.getMonth()), 0);
  return { term_years: String(Math.floor(left / 12)), term_months: String(left % 12) };
}

/** Whole months from `ym` to this month. */
function monthsSince(ym) {
  if (!ym) return 0;
  const [y, m] = ym.split('-').map(Number);
  const now = new Date();
  return Math.max((now.getFullYear() * 12 + now.getMonth()) - (y * 12 + m - 1), 0);
}

function thisMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function complete(form) {
  return Number(form.balance) > 0 && form.rate !== '' && totalMonths(form) >= 12;
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
            <label htmlFor="mg-years">Left to pay</label>
            <span className="row" style={{ gap: 6 }}>
              <input id="mg-years" type="number" min="0" max="40" step="1" required
                     inputMode="numeric" value={form.years}
                     onChange={set('years')} style={{ width: 70 }} />
              <span className="muted">years</span>
              <label htmlFor="mg-months" className="sr-only">Months left to pay</label>
              <input id="mg-months" type="number" min="0" max="11" step="1"
                     inputMode="numeric" value={form.months} placeholder="0"
                     onChange={set('months')} style={{ width: 64 }} />
              <span className="muted">months</span>
            </span>
          </div>

          <div className="controls">
            <label htmlFor="mg-frequency">How often you pay</label>
            <select id="mg-frequency" value={form.frequency} onChange={set('frequency')}>
              {Object.entries(FREQUENCY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <label htmlFor="mg-payment">Your payment</label>
            <span className="row" style={{ gap: 4 }}>
              <span className="muted">$</span>
              <input id="mg-payment" type="number" min="0" step="any" inputMode="decimal"
                     value={form.actual_payment}
                     placeholder={r?.worked_out_payment ? String(r.worked_out_payment) : ''}
                     onChange={set('actual_payment')} style={{ width: 110 }}
                     aria-describedby="mg-payment-hint" />
              <span className="muted">{PER_PAYMENT[form.frequency]}</span>
            </span>
          </div>

          <div className="controls">
            <label htmlFor="mg-term-years">Term left</label>
            <span className="row" style={{ gap: 6 }}>
              <input id="mg-term-years" type="number" min="0" max="10" step="1"
                     inputMode="numeric" value={form.term_years} placeholder="0"
                     onChange={set('term_years')} style={{ width: 64 }}
                     aria-describedby="mg-term-hint" />
              <span className="muted">years</span>
              <label htmlFor="mg-term-months" className="sr-only">Months of the term left</label>
              <input id="mg-term-months" type="number" min="0" max="11" step="1"
                     inputMode="numeric" value={form.term_months} placeholder="0"
                     onChange={set('term_months')} style={{ width: 64 }} />
              <span className="muted">months</span>
            </span>
            <label htmlFor="mg-original">Original mortgage</label>
            <span className="row" style={{ gap: 4 }}>
              <span className="muted">$</span>
              <input id="mg-original" type="number" min="0" step="any" inputMode="decimal"
                     value={form.original} placeholder="optional"
                     onChange={set('original')} style={{ width: 120 }} />
            </span>
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
          <div className="controls">
            <label className="row small" style={{ gap: 6, color: 'inherit' }}>
              <input type="checkbox" checked={form.shared}
                     onChange={(e) => setForm({ ...form, shared: e.target.checked })} />
              Shared
            </label>
            {form.shared && (
              <>
                <label className="row small" style={{ gap: 6, color: 'inherit' }}>
                  <input type="radio" name="mg-share-mode" value="percent"
                         checked={form.share_mode === 'percent'}
                         onChange={set('share_mode')} />
                  A percentage
                </label>
                <label className="row small" style={{ gap: 6, color: 'inherit' }}>
                  <input type="radio" name="mg-share-mode" value="amount"
                         checked={form.share_mode === 'amount'}
                         onChange={set('share_mode')} />
                  A fixed amount
                </label>
                <label htmlFor="mg-share" className="sr-only">
                  {form.share_mode === 'percent' ? 'Your share, percent' : 'Your share, a month'}
                </label>
                <span className="row" style={{ gap: 4 }}>
                  {form.share_mode === 'amount' && <span className="muted">$</span>}
                  <input id="mg-share" type="number" min="0" step="any" inputMode="decimal"
                         max={form.share_mode === 'percent' ? 100 : undefined}
                         value={form.share_value} onChange={set('share_value')}
                         style={{ width: 100 }} />
                  <span className="muted">
                    {form.share_mode === 'percent' ? '% is yours' : 'a month is yours'}
                  </span>
                </span>
              </>
            )}
          </div>
          {form.shared && r?.share && (
            <p className="small" style={{ margin: 0 }}>
              You pay <strong className="num">{money(r.your_monthly, { cents: true })}</strong>{' '}
              a month of <span className="num">{money(r.committed_monthly, { cents: true })}</span>{' '}
              ({pct(r.share.fraction)})
            </p>
          )}

          <StatementCheck r={r} form={form} />

          <PayoffNote r={r} form={form} />


          {data.existing && !data.saved && (
            <Notice>
              Replaces your {money(data.existing.amount, { cents: true })}{' '}
              {data.existing.name} line
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
            {dirty && complete(form) && <span className="small muted">Not saved</span>}
          </div>
        </form>
      </Card>

      {r && <Results data={shown} r={r} form={form} setForm={setForm}
                     onTab={onTab} />}
    </div>
  );
}

/**
 * Does the payment square with the years left? A statement's remaining
 * amortization is worked out from its payment, so the two should agree to
 * within a month; if they don't, one of the figures was mistyped.
 */
function StatementCheck({ r, form }) {
  if (!r) return null;
  const per = PER_PAYMENT[r.frequency];
  if (r.payment_source !== 'statement') {
    return (
      <p id="mg-payment-hint" className="small muted" style={{ margin: 0 }}>
        <span className="num">{money(r.worked_out_payment, { cents: true })}</span> {per}
      </p>
    );
  }
  const months = r.amortization_months;
  const off = months == null ? null : Math.abs(months - r.typed_months);
  const paidOff = months == null ? null : yearsMonths(Math.round(months));
  return (
    <p id="mg-payment-hint" className="small" style={{ margin: 0 }}>
      {off != null && off <= 1.5 ? (
        <>✓ {paidOff} left at <span className="num">{money(r.payment, { cents: true })}</span> {per}</>
      ) : (
        <>At <span className="num">{money(r.payment, { cents: true })}</span> {per}:{' '}
          <strong>{paidOff}</strong> left, not {yearsMonths(r.typed_months)}</>
      )}
    </p>
  );
}

/**
 * Why the payoff can be sooner than the years typed, and how old the typed
 * figures are — said, rather than quietly written back into the boxes.
 */
function PayoffNote({ r, form }) {
  if (!r) return null;
  const typedLeft = totalMonths(form) - monthsSince(r.as_of);
  const sooner = typedLeft - r.months_left;
  const reasons = [];
  if (r.accelerated) {
    reasons.push('accelerated payments add a 13th monthly payment a year');
  }
  if (r.extra_monthly > 0) reasons.push(`of the extra ${money(r.extra_monthly)} a month`);
  const old = r.as_of && r.as_of < thisMonth()
    && Number(form.balance) === Number(form.as_of_balance)
    && totalMonths(form) === Number(form.as_of_months);

  if (!(sooner > 1 && reasons.length) && !old) return null;
  return (
    <p className="small" style={{ margin: 0 }}>
      {sooner > 1 && reasons.length > 0 && (
        <>Paid off in <strong>{yearsMonths(r.months_left)}</strong>{' '}
          ({r.accelerated ? 'accelerated' : `+${money(r.extra_monthly)}/mo`}) </>
      )}
      {old && (
        <span className="muted">As of {monthLabel(r.as_of, { long: true })}</span>
      )}
    </p>
  );
}

function Results({ data, r, form, setForm, onTab }) {
  const paidOffIn = yearsMonths(r.months_left);
  const interestShare = r.interest_share;
  // Shared: your part leads, the whole loan beside it. The payoff date and
  // the chart stay whole, because it is one loan.
  const sh = r.share?.shared ? r.share : null;
  const ofIncome = data.share_of_income != null
    ? `${pct(data.share_of_income)} of your take-home pay`
    : 'Set your take-home on Income to see the share';

  return (
    <>
      <div className="grid cols-4">
        {sh ? (
          <>
            <Tile label="Your share each month" value={money(r.your_monthly)}
                  note={`of ${money(r.committed_monthly)} · ${ofIncome}`} />
            <Tile label="Paid off by" value={monthLabel(r.payoff_month)}
                  note={`${paidOffIn} from now`} />
            <Tile label="Your share of the interest" value={money(sh.interest)}
                  note={`of ${money(r.total_interest)} in all`} />
            <Tile label="Your share of what's owed" value={money(sh.balance_now)}
                  note={`of ${money(r.balance_now)}`} />
          </>
        ) : (
          <>
            <Tile label="Out of every month" value={money(r.committed_monthly)}
                  note={ofIncome} />
            <Tile label="Paid off by" value={monthLabel(r.payoff_month)}
                  note={`${paidOffIn} from now`} />
            <Tile label="Interest still to pay" value={money(r.total_interest)}
                  note={`on ${money(r.total_principal)} owing`} />
            <Tile label="Owing now" value={money(r.balance_now)}
                  note={r.as_of && r.balance_now !== Number(form.balance)
                    ? `rolled forward from ${monthLabel(r.as_of)}`
                    : `${money(r.payment, { cents: true })} ${PER_PAYMENT[r.frequency]}`} />
          </>
        )}
      </div>

      <Card title="Interest against principal">
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
        {r.original && (
          <p className="small" style={{ margin: '10px 0 0' }}>
            Paid off <strong className="num">{money(r.paid_so_far)}</strong>{' '}
            of {money(r.original)} ({pct(r.paid_so_far_share)})
            {sh && <> · yours {money(r.paid_so_far * sh.fraction)}</>}
          </p>
        )}
        <p className="small muted" style={{ margin: '10px 0 0' }}>
          {money(r.total_paid)} to pay
          {sh && <> · yours {money(sh.principal)} + {money(sh.interest)} interest</>}
        </p>
      </Card>

      <ExtraSlider r={r} form={form} setForm={setForm} />

      <InvestOrPayDown form={form} savings={data.savings} onTab={onTab} />

      <Card title="Where each year's payments go">
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
      </Card>

      <Card title="Shorter or longer">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paid off over</th>
                <th className="r">Payment</th>
                <th className="r">A month</th>
                {sh && <th className="r">Your share</th>}
                <th className="r">Total interest</th>
              </tr>
            </thead>
            <tbody>
              {r.alternatives.map((a) => {
                const current = a.years * 12 === totalMonths(form);
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
                    {sh && <td className="r num">{money(a.your_monthly)}</td>}
                    <td className="r num">{money(a.total_interest)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
    <Card title="Paying extra">
      <div className="controls" style={{ alignItems: 'center', gap: 14 }}>
        <label htmlFor="mg-extra" style={{ whiteSpace: 'nowrap' }}>
          {r.share?.shared ? 'Extra each month, between you' : 'Extra each month'}
        </label>
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
              interest</>
          : null}
      </p>
    </Card>
  );
}

/**
 * Should the extra go into investments or onto the mortgage?
 *
 * Asked of the server for whatever terms are on screen. Both worlds spend the
 * same every month until the mortgage would have ended anyway; the page
 * reports which ends up with more, and the return at which they tie.
 */
function InvestOrPayDown({ form, savings, onTab }) {
  const [opts, setOpts] = useState({
    monthly: savings > 0 ? String(savings) : '500',
    lump: '', expected: '5', account: 'sheltered', marginal: '',
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const set = (key) => (e) => setOpts({ ...opts, [key]: e.target.value });

  useEffect(() => {
    if (!complete(form)) { setResult(null); return undefined; }
    const id = setTimeout(async () => {
      try {
        setResult(await compareMortgage(body(form), {
          monthly: Number(opts.monthly) || 0,
          lump: Number(opts.lump) || 0,
          expected: Number(opts.expected) || 0,
          account: opts.account,
          marginal: Number(opts.marginal) || 0,
        }));
        setError(null);
      } catch (e) {
        setError(e);
      }
    }, 250);
    return () => clearTimeout(id);
  }, [form, opts]);

  const c = result;
  const ahead = c && Math.abs(c.difference);

  return (
    <Card title="Invest it, or pay down the mortgage?">
      <div className="controls">
        <label htmlFor="ip-monthly">Extra each month</label>
        <input id="ip-monthly" type="number" min="0" step="any" inputMode="decimal"
               value={opts.monthly} onChange={set('monthly')} style={{ width: 110 }} />
        <label htmlFor="ip-lump">Lump sum now</label>
        <input id="ip-lump" type="number" min="0" step="any" inputMode="decimal"
               value={opts.lump} placeholder="0" onChange={set('lump')}
               style={{ width: 120 }} />
        <label htmlFor="ip-return">Expected return</label>
        <span className="row" style={{ gap: 4 }}>
          <input id="ip-return" type="number" min="0" max="20" step="any"
                 inputMode="decimal" value={opts.expected} onChange={set('expected')}
                 style={{ width: 80 }} />
          <span className="muted">% a year</span>
        </span>
      </div>
      <div className="controls" style={{ marginTop: 10 }}>
        <label>Invested in</label>
        <label className="row small" style={{ gap: 6, color: 'inherit' }}>
          <input type="radio" name="ip-account" value="sheltered"
                 checked={opts.account === 'sheltered'} onChange={set('account')} />
          A TFSA or RRSP
        </label>
        <label className="row small" style={{ gap: 6, color: 'inherit' }}>
          <input type="radio" name="ip-account" value="taxable"
                 checked={opts.account === 'taxable'} onChange={set('account')} />
          A taxable account
        </label>
        {opts.account === 'taxable' && (
          <>
            <label htmlFor="ip-marginal">Marginal tax rate</label>
            <span className="row" style={{ gap: 4 }}>
              <input id="ip-marginal" type="number" min="0" max="60" step="any"
                     inputMode="decimal" value={opts.marginal} placeholder="43"
                     onChange={set('marginal')} style={{ width: 80 }} />
              <span className="muted">%</span>
            </span>
          </>
        )}
      </div>


      <ErrorNote error={error} />

      {c && (
        <>
          <Notice kind={c.winner === 'tie' ? '' : 'good'}>
            <strong>
              {c.winner === 'tie'
                ? `At ${pctRate(c.expected)}, it's a wash.`
                : c.winner === 'invest'
                  ? `At ${pctRate(c.expected)}, investing comes out ${money(ahead)} ahead`
                  : `At ${pctRate(c.expected)}, paying down the mortgage comes out ${money(ahead)} ahead`}
            </strong>
            {c.winner !== 'tie' && <> by {monthLabel(c.horizon_month, { long: true })}</>}
            {c.breakeven != null && (
              <div className="small muted" style={{ marginTop: 4 }}>
                Break-even {c.breakeven > 0 ? pctRate(c.breakeven) : '0%'}
                {c.tax_on_growth > 0 && ' before tax'}
              </div>
            )}
          </Notice>

          <div className="grid cols-2" style={{ marginTop: 14 }}>
            <Tile label="If you invest it" value={money(c.invest)}
                  note={`by ${monthLabel(c.horizon_month)}`} />
            <Tile label="If you pay it down" value={money(c.prepay)}
                  note={`mortgage gone ${monthLabel(c.paid_off_month)} · ${
                    money(c.interest_saved)} less interest`} />
          </div>

          <div className="chart" style={{ marginTop: 16 }}>
            <Chart config={investOrPayDownConfig(c.series)}
                   ariaLabel={`How far ahead investing is over paying down, year by year, at ${
                     pctRate(c.expected)}. By ${monthLabel(c.horizon_month, { long: true })}: ${
                     c.difference >= 0 ? 'investing' : 'paying down'} ahead by ${money(ahead)}.`} />
          </div>

          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table>
              <thead>
                <tr><th>If investments returned</th>
                  <th className="r">Invest</th><th className="r">Pay down</th>
                  <th className="r">Better by</th></tr>
              </thead>
              <tbody>
                {c.rates.map((x) => (
                  <tr key={x.rate}>
                    <td>{x.label} <span className="muted small">{pctRate(x.rate)}</span></td>
                    <td className="r num">{money(x.invest)}</td>
                    <td className="r num">{money(x.prepay)}</td>
                    <td className="r num">
                      {money(Math.abs(x.difference))}{' '}
                      <span className="muted small">
                        {x.difference >= 0 ? 'investing' : 'paying down'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </>
      )}
    </Card>
  );
}

function pctRate(fraction) {
  return `${(Math.round(fraction * 10000) / 100).toFixed(2).replace(/\.?0+$/, '')}%`;
}

function yearsMonths(months) {
  const y = Math.floor(months / 12);
  const m = months % 12;
  const parts = [];
  if (y) parts.push(`${y} year${y === 1 ? '' : 's'}`);
  if (m || !y) parts.push(`${m} month${m === 1 ? '' : 's'}`);
  return parts.join(' ');
}
