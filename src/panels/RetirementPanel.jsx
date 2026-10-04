import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, Tile, Why,
} from '../components/ui.jsx';
import {
  clearCoastfire, getCoastfire, money, monthLabel, pct, previewCoastfire,
  saveCoastfire,
} from '../api.js';
import { coastConfig } from '../charts.js';

/**
 * Retirement: the CoastFIRE calculator.
 *
 * How much has to be invested now for it to grow, untouched, into enough to
 * retire on — and when, at the rate you are saving, you get there. Saved so
 * it is typed once, but it changes nothing else: the plan decides what you
 * save, this only says what that saving adds up to.
 *
 * Every figure comes from the server, the form asking it for a preview a
 * moment after you stop typing.
 */

const FIELDS = ['age', 'retire_age', 'invested', 'spending', 'pension',
                'withdrawal', 'real_return', 'monthly'];

function fromSaved(data) {
  const s = data?.saved;
  const r = data?.result;
  const d = data?.defaults ?? {};
  if (!s || !r) {
    return {
      age: '', retire_age: '65', invested: '',
      spending: d.plan_spending ? String(d.plan_spending) : '',
      pension: '0', withdrawal: '4', real_return: '5',
      monthly: d.plan_saving ? String(d.plan_saving) : '0',
    };
  }
  return {
    age: String(r.age), retire_age: String(s.retire_age),
    invested: String(s.invested), spending: String(s.spending),
    pension: String(s.pension), withdrawal: String(s.withdrawal),
    real_return: String(s.real_return), monthly: String(s.monthly),
  };
}

function body(form) {
  return Object.fromEntries(FIELDS.map((k) => [k, Number(form[k]) || 0]));
}

function complete(form) {
  return Number(form.age) > 0 && Number(form.spending) > 0
    && Number(form.retire_age) > Number(form.age);
}

export default function RetirementPanel({ onTab }) {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoadError(null);
    try {
      const d = await getCoastfire();
      setData(d);
      const f = fromSaved(d);
      setForm(f);
      setSaved(f);
      setPreview(null);
    } catch (e) {
      setLoadError(e);
    }
  }

  useEffect(() => { load(); }, []);

  const dirty = useMemo(
    () => form && saved && JSON.stringify(body(form)) !== JSON.stringify(body(saved)),
    [form, saved]);

  useEffect(() => {
    if (!form || !complete(form) || (!dirty && data?.result)) {
      setPreview(null);
      return undefined;
    }
    const id = setTimeout(async () => {
      try {
        setPreview((await previewCoastfire(body(form))).result);
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
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <ErrorNote error={loadError} onRetry={load} />;
  if (!data || !form) return <Loading what="your retirement figures" />;

  const r = preview ?? data.result;
  const d = data.defaults ?? {};
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  // A mortgage paid off before retirement is a cost retirement won't have.
  const yearsLeft = Number(form.retire_age) - Number(form.age);
  const retireYear = new Date().getFullYear() + (Number.isFinite(yearsLeft) ? yearsLeft : 0);
  const mortgageEnds = d.mortgage
    && Number(d.mortgage.payoff_month.slice(0, 4)) <= retireYear;
  const withoutMortgage = d.plan_spending && d.mortgage
    ? Math.max(d.plan_spending - d.mortgage.yearly, 0) : null;

  return (
    <div className="stack">
      <Card title="Your retirement figures"
            hint="Typed once and remembered — it changes nothing else in your plan"
            actions={data.saved && !dirty && (
              <button className="btn quiet" disabled={busy}
                      onClick={() => run(clearCoastfire)}>
                Clear
              </button>
            )}>
        <ErrorNote error={error} />
        <form className="stack" style={{ gap: 14 }} onSubmit={(e) => {
          e.preventDefault();
          run(() => saveCoastfire(body(form)));
        }}>
          <div className="controls">
            <label htmlFor="cf-age">Your age</label>
            <input id="cf-age" type="number" min="16" max="90" step="any" required
                   inputMode="decimal" value={form.age} placeholder="32"
                   onChange={set('age')} style={{ width: 80 }} />
            <label htmlFor="cf-retire">Retire at</label>
            <input id="cf-retire" type="number" min="17" max="100" step="any" required
                   inputMode="decimal" value={form.retire_age}
                   onChange={set('retire_age')} style={{ width: 80 }} />
            <label htmlFor="cf-invested">Invested for retirement now</label>
            <input id="cf-invested" type="number" min="0" step="any" inputMode="decimal"
                   value={form.invested} placeholder="0"
                   onChange={set('invested')} style={{ width: 130 }} />
          </div>

          <div className="controls">
            <label htmlFor="cf-spending">A year of retirement costs</label>
            <input id="cf-spending" type="number" min="1" step="any" required
                   inputMode="decimal" value={form.spending}
                   onChange={set('spending')} style={{ width: 130 }} />
            <label htmlFor="cf-pension">Pensions a year</label>
            <input id="cf-pension" type="number" min="0" step="any" inputMode="decimal"
                   value={form.pension} onChange={set('pension')} style={{ width: 110 }}
                   aria-describedby="cf-pension-hint" />
            <label htmlFor="cf-monthly">Saving for it each month</label>
            <input id="cf-monthly" type="number" min="0" step="any" inputMode="decimal"
                   value={form.monthly} onChange={set('monthly')} style={{ width: 110 }} />
          </div>

          <div className="controls">
            <label htmlFor="cf-return">Return after inflation</label>
            <span className="row" style={{ gap: 4 }}>
              <input id="cf-return" type="number" min="0" max="15" step="any"
                     inputMode="decimal" value={form.real_return}
                     onChange={set('real_return')} style={{ width: 80 }} />
              <span className="muted">% a year</span>
            </span>
            <label htmlFor="cf-withdrawal">Withdrawal rate</label>
            <span className="row" style={{ gap: 4 }}>
              <input id="cf-withdrawal" type="number" min="2" max="10" step="any"
                     inputMode="decimal" value={form.withdrawal}
                     onChange={set('withdrawal')} style={{ width: 80 }} />
              <span className="muted">%</span>
            </span>
          </div>

          <p id="cf-pension-hint" className="small muted" style={{ margin: 0 }}>
            {d.plan_spending
              ? <>The yearly cost starts from your plan — take-home less saving,
                  {' '}{money(d.plan_spending)} a year — and the monthly saving
                  from the {money(d.plan_saving)} it sets aside. </>
              : <>Set your take-home on{' '}
                  <GoTo to="plan" from="retirement" onTab={onTab} /> and the
                  yearly cost can start from your plan. </>}
            Pensions are CPP, OAS or a workplace pension: whatever arrives
            without the portfolio paying it. Everything is in today&apos;s
            dollars.
          </p>

          {mortgageEnds && withoutMortgage != null
            && Number(form.spending) !== withoutMortgage && (
            <Notice>
              Your mortgage is paid off by{' '}
              {monthLabel(d.mortgage.payoff_month, { long: true })}, before you
              would retire, so its {money(d.mortgage.yearly)} a year won&apos;t
              be a cost then.{' '}
              <button type="button" className="link"
                      onClick={() => setForm({ ...form, spending: String(withoutMortgage) })}>
                Take it out — {money(withoutMortgage)} a year
              </button>
            </Notice>
          )}

          <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
            <button className="btn primary" type="submit"
                    disabled={busy || !complete(form) || (!dirty && data.saved)}>
              {busy ? 'Saving…' : data.saved ? 'Save changes' : 'Save'}
            </button>
            {dirty && data.saved && (
              <button className="btn quiet" type="button" onClick={() => setForm(saved)}>
                Undo changes
              </button>
            )}
            {dirty && (
              <span className="small muted">
                {complete(form) ? 'A preview — nothing is saved until you press Save.'
                  : 'Fill in your age and what a year would cost to see it worked out.'}
              </span>
            )}
          </div>
        </form>
      </Card>

      {r && <Results r={r} onTab={onTab} />}
    </div>
  );
}

function Results({ r, onTab }) {
  const years = (age) => Math.floor(age);

  return (
    <>
      <Verdict r={r} />

      <div className="grid cols-4">
        <Tile label="Your FIRE number" value={money(r.fire_number)}
              note={`${money(r.from_portfolio)} a year at ${r.withdrawal}%`} />
        <Tile label="Coast number today" value={money(r.coast_number)}
              note={`grows into it by ${r.retire_age} at ${r.real_return}% a year`} />
        <div className="card tile">
          <div className="label">Invested now</div>
          <div className="value num">{money(r.invested)}</div>
          <div className="meter" role="img"
               aria-label={`${pct(r.progress)} of the coast number`}>
            <span style={{ width: `${r.progress * 100}%` }} />
          </div>
          <div className="note">
            {pct(r.progress)} of the coast number · as of {monthLabel(r.as_of)}
          </div>
        </div>
        <Tile label="Fully retired at" value={r.fire_age != null ? String(years(r.fire_age)) : '—'}
              note={r.fire_age != null
                ? `if you keep saving ${money(r.monthly)} a month`
                : 'not by 100 at this rate'} />
      </div>

      <Card title="When you could stop saving"
            hint="In today's dollars — where the lines cross is your coast age">
        <div className="chart">
          <Chart config={coastConfig(r.series)}
                 ariaLabel={`Needed to coast, rising to ${money(r.fire_number)} at ${
                   r.retire_age}, against your investments, reaching ${
                   money(r.at_retirement)}. ${r.coast_age != null
                   ? `They cross at ${years(r.coast_age)}.` : 'They do not cross before retirement.'}`} />
        </div>
        <div className="legend" style={{ marginTop: 6 }}>
          <span className="item">
            <span className="swatch" style={{ background: 'var(--series-1)' }} />
            Your investments, saving {money(r.monthly)} a month
          </span>
          <span className="item">
            <span className="swatch dashed" style={{ borderColor: 'var(--series-3)' }} />
            Needed to coast — {money(r.fire_number)} by {r.retire_age}
          </span>
        </div>
      </Card>

      <Card title="At other returns" hint="The return is the assumption that matters most">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>After inflation</th>
                <th className="r">Coast number</th>
                <th className="r">Coasting at</th>
                <th className="r">Fully retired at</th>
              </tr>
            </thead>
            <tbody>
              {r.rates.map((x) => {
                const current = Math.abs(x.rate * 100 - r.real_return) < 0.001;
                return (
                  <tr key={x.rate} className={current ? 'current' : ''}>
                    <td>
                      {Math.round(x.rate * 100)}% a year
                      {current && <span className="muted small"> · yours</span>}
                    </td>
                    <td className="r num">{money(x.coast_number)}</td>
                    <td className="r num">
                      {x.coast_age != null
                        ? (x.coast_month === 0 ? 'already' : years(x.coast_age))
                        : <span className="muted">not before {r.retire_age}</span>}
                    </td>
                    <td className="r num">
                      {x.fire_age != null ? years(x.fire_age) : <span className="muted">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Why id="retirement.coast" label="What this assumes">
          <ul className="steps" style={{ margin: 0 }}>
            <li><strong>CoastFIRE</strong> means what you have invested will
              grow, untouched, into your FIRE number by {r.retire_age}. From
              then on, work only has to pay for today; anything more you save
              makes retirement earlier rather than possible.</li>
            <li><strong>Today&apos;s dollars.</strong> The return is after
              inflation, so a long-run stock return of 7–8% is roughly 4–5%
              here. That keeps every figure meaning what it means now.</li>
            <li><strong>The withdrawal rate.</strong> 4% comes from US
              studies of 30-year retirements. A longer retirement, or one that
              starts in a bad market, calls for less — 3.5% is the cautious
              choice.</li>
            <li><strong>Pensions.</strong> CPP and OAS depend on your
              contributions and the age you start them; your estimate is in
              My Service Canada Account.</li>
            <li><strong>Not modelled:</strong> taxes on withdrawals (an RRSP is
              taxed coming out; a TFSA isn&apos;t), fees, or a return that
              arrives as good years and bad ones in an order nobody chooses.
              It is arithmetic, not advice.</li>
          </ul>
          <p className="small muted" style={{ marginBottom: 0 }}>
            What you save each month is set on{' '}
            <GoTo to="plan" from="retirement" onTab={onTab} />.
          </p>
        </Why>
      </Card>
    </>
  );
}

function Verdict({ r }) {
  const age = (a) => Math.floor(a);
  const need = r.needed_monthly;

  if (r.coasting) {
    return (
      <Notice kind="good">
        <strong>You&apos;re coasting.</strong> {money(r.invested)} grows to{' '}
        {money(r.untouched_at_retirement)} by {r.retire_age} without another
        dollar — your FIRE number is {money(r.fire_number)}.
        {r.early_retire_age != null && r.early_retire_age < r.retire_age && (
          <> Left alone it gets there at {age(r.early_retire_age)}; anything you
            keep saving brings that sooner.</>
        )}
      </Notice>
    );
  }
  if (r.coast_age != null) {
    return (
      <Notice kind="good">
        <strong>
          You&apos;ll reach CoastFIRE at {age(r.coast_age)}, in{' '}
          {monthLabel(r.coast_month, { long: true })}
        </strong>
        , saving {money(r.monthly)} a month — {money(r.contributed_to_coast)} more
        in all. After that, saving for retirement is optional: what you have
        grows into {money(r.fire_number)} by {r.retire_age} on its own.
      </Notice>
    );
  }
  return (
    <Notice>
      <strong>At {money(r.monthly)} a month you won&apos;t coast before {r.retire_age}.</strong>
      {r.fire_age != null && <> You&apos;d reach your FIRE number at {age(r.fire_age)}.</>}
      {need?.to_coast != null && (
        <> To coast within {Math.round(need.coast_years)} years you&apos;d need to
          save <strong className="num">{money(need.to_coast)}</strong> a month
          {need.to_fire_by_retirement != null && (
            <>; to be fully retired at {r.retire_age},{' '}
              <strong className="num">{money(need.to_fire_by_retirement)}</strong></>
          )}.</>
      )}
    </Notice>
  );
}
