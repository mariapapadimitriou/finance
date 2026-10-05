import { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart.jsx';
import {
  Card, ErrorNote, GoTo, Loading, Notice, Tile, } from '../components/ui.jsx';
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
                   />
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


          {mortgageEnds && withoutMortgage != null
            && Number(form.spending) !== withoutMortgage && (
            <Notice>
              Mortgage paid off {monthLabel(d.mortgage.payoff_month)} ·{' '}
              <button type="button" className="link"
                      onClick={() => setForm({ ...form, spending: String(withoutMortgage) })}>
                Take out {money(d.mortgage.yearly)}/yr
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
            {dirty && complete(form) && <span className="small muted">Not saved</span>}
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

      <Card title="When you could stop saving">
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

      <Card title="At other returns">
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
        <strong>You&apos;re coasting</strong> · {money(r.untouched_at_retirement)} by{' '}
        {r.retire_age}
        {r.early_retire_age != null && r.early_retire_age < r.retire_age && (
          <> · FIRE at {age(r.early_retire_age)}</>
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
        {' '}· {money(r.monthly)} a month
      </Notice>
    );
  }
  return (
    <Notice>
      <strong>Not coasting before {r.retire_age}</strong>
      {need?.to_coast != null && (
        <div className="small" style={{ marginTop: 4 }}>
          Coast in {Math.round(need.coast_years)} years:{' '}
          <strong className="num">{money(need.to_coast)}</strong>/mo
          {need.to_fire_by_retirement != null && (
            <> · retire at {r.retire_age}:{' '}
              <strong className="num">{money(need.to_fire_by_retirement)}</strong>/mo</>
          )}
        </div>
      )}
    </Notice>
  );
}
