import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getProjections } from '../api.js';
import { PButton, StatusPill } from '../pearl/kit.jsx';
import {
  onProjectionsUrl, readProjectionsUrl, setGoalsIntent, writeLearnUrl, writePathUrl, writeProjectionsUrl,
} from '../router.js';
import { More } from './InsightsParts.jsx';
import PIcon from '../pearl/icons.jsx';
import { ForecastChart, Next30Chart, SavingsChart } from './ProjectionsCharts.jsx';
import { ForecastView, Next30View, SavingsView } from './ProjectionsViews.jsx';
import UnveilScreens from './Unveil.jsx';
import {
  CALC_START, anchorLine, calculator, dollarsWords, forecastLine, next30Line, parseAmount, parseYears,
  savingsWords,
} from './projectionsMath.js';
import './home.css';
import './insights.css';
import './projections.css';

/**
 * Save › Projections (Pearl THL-197 GR-33, at /save/projections; moved from
 * Growth by THL-248). It replaced the prototype Projections page and the
 * "leave a transaction out" manager it held (leave-out rules live in
 * Profile › Categories and rules).
 *
 * GR-33 is the GR-17 layout — a way back to Save, YOUR ANCHOR and the growth
 * calculator (THL-135 GR-17, GR-18) — with three look-ahead cards between the
 * Anchor line and the calculator, each opening its detail view at its own
 * address: GR-34 this month (/forecast, THL-191), GR-35 the next 30 days
 * (/next30, THL-192) and GR-36 savings in a year (/savings, THL-194). GR-17
 * itself, the calculator without the cards, is /save/calculator, which Save's
 * "Open the calculator" and GR-16's "Try the growth calculator" open.
 *
 * The investing screens are here too, reached from Wins: GR-16 Ready to
 * invest (/save/ready), GR-37 "Opened an investing account?"
 * (/save/invested) and GR-10, done (/save/invested/done) — Unveil.jsx.
 *
 * Every projection is a range, every chart has a table for a screen reader,
 * nothing is red and nothing is signed. "Learn how fees change this" opens
 * Learn's Fees module (THL-134).
 */

const VIEWS = { forecast: ForecastView, next30: Next30View, savings: SavingsView };
const UNVEIL = ['ready', 'unveil', 'done'];

export default function ProjectionsPanel({ onTab, onChanged, version }) {
  const [route, setRoute] = useState(() => readProjectionsUrl() ?? { view: '' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const unveil = UNVEIL.includes(route.view);

  useEffect(() => onProjectionsUrl(() => {
    const next = readProjectionsUrl();
    if (next) setRoute(next);
  }), []);

  const load = useCallback(() => {
    setError(null);
    return getProjections().then(setData).catch(setError);
  }, []);
  useEffect(() => { if (!unveil) load(); }, [load, version, unveil]);

  const show = (view = '') => {
    writeProjectionsUrl(view);
    window.scrollTo?.({ top: 0 });
  };
  const nav = {
    show, onTab, onChanged, reload: load, setData,
    toGoals: (view) => { setGoalsIntent({ view }); onTab?.('goals'); },
    toLearn: (module = '', from = '') => { writeLearnUrl({ module, from }); onTab?.('learn'); },
    toStep: (step) => { writePathUrl({ step }); onTab?.('path'); },
  };

  if (unveil) return <UnveilScreens view={route.view} nav={nav} version={version} />;
  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) {
    return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your projections…</p></div>;
  }
  const View = VIEWS[route.view];
  if (View) return <View d={data} nav={nav} />;
  return <ProjectionsPage d={data} nav={nav} cards={route.view !== 'calculator'} />;
}

/** "YOUR ANCHOR · Likely full between March and June 2027 · See the projection ›". */
export function AnchorLine({ anchor, nav }) {
  const line = anchorLine(anchor);
  return (
    <section className="hm-card pj-anchor" aria-labelledby="pj-anchor-title">
      <div className="in-stack">
        <p className="pk-overline">Your Anchor</p>
        <h2 className="pk-h3" id="pj-anchor-title">{line.text}</h2>
      </div>
      <More onClick={() => nav.toGoals(line.view)}>{line.link}</More>
    </section>
  );
}

function CardHead({ title, id, link, onLink, label }) {
  return (
    <div className="in-card-head">
      <h2 className="pk-h3" id={id}>{title}</h2>
      <More onClick={onLink} label={label}>{link}</More>
    </div>
  );
}

/** "‹ Save": back to the Save page. */
export function BackToSave({ onTab }) {
  return (
    <div className="in-back-row">
      <button type="button" className="in-back" onClick={() => onTab?.('goals')}>
        <PIcon name="chevronRight" size={12} className="in-flip" /> Save
      </button>
    </div>
  );
}

/** GR-33 (and GR-17, the calculator on its own, without the look-ahead cards). */
export function ProjectionsPage({ d, nav, cards = true }) {
  const f = d.forecast;
  const n = d.next30;
  const s = d.savings;
  const words = savingsWords(s);
  return (
    <div className="pk hm-page in-page pj-page">
      <BackToSave onTab={nav.onTab} />
      <header className="hm-head">
        <p className="pk-overline accent">{cards ? 'What could happen' : 'Illustrative, to help you plan'}</p>
        <h1 className="pk-h1">{cards ? 'Projections' : 'Growth calculator'}</h1>
      </header>
      {cards && <AnchorLine anchor={d.anchor} nav={nav} />}

      {cards && (
        <div className="pj-cards">
          <section className="hm-card in-card" aria-labelledby="pj-month-title">
            <CardHead id="pj-month-title" title="This month" link="See the forecast"
                      onLink={() => nav.show('forecast')} label="See the forecast for this month" />
            <p className="pj-body">{forecastLine(f)}</p>
            {f.state !== 'none' && <ForecastChart f={f} />}
          </section>
          <div className="pj-row">
            <section className="hm-card in-card" aria-labelledby="pj-next-title">
              <CardHead id="pj-next-title" title="The next 30 days" link="See all"
                        onLink={() => nav.show('next30')} label="See all of the next 30 days" />
              <p className="pj-body">{next30Line(n)}</p>
              {(n.series.length > 0 || n.events.length > 0) && <Next30Chart n={n} />}
            </section>
            <section className="hm-card in-card" aria-labelledby="pj-savings-title">
              <CardHead id="pj-savings-title" title="Your savings in a year" link="See more"
                        onLink={() => nav.show('savings')} label="See more of your savings in a year" />
              <p className="pk-h2 pj-figure-big">{words.figure}</p>
              <p className="pk-label pk-muted">{words.line}</p>
              {s.state === 'ok' && <SavingsChart s={s} />}
            </section>
          </div>
        </div>
      )}

      <Calculator onReady={() => nav.show('ready')} onLearn={() => nav.toLearn?.('fees')} />
    </div>
  );
}

/**
 * GR-17 and GR-18: what regular investing could grow to at 3%, 5% and 7%.
 * Illustrative, not a prediction: it uses only the two figures she types.
 * Once she changes one, "Ready to invest" appears (GR-18).
 */
export function Calculator({ onReady, onLearn, initial = CALC_START }) {
  const [monthly, setMonthly] = useState(`$${initial.monthly}`);
  const [years, setYears] = useState(`${initial.years} years`);
  const amount = parseAmount(monthly);
  const span = parseYears(years);
  const result = calculator(amount, span);
  const changed = amount !== Number(initial.monthly) || span !== Number(initial.years);
  return (
    <section className="hm-card in-card pj-calc" aria-labelledby="pj-calc-title">
      <div className="in-stack pj-calc-head">
        <StatusPill icon="info" tone="info">Illustrative · not a prediction</StatusPill>
        <h2 className="pk-h2" id="pj-calc-title">What regular investing could grow to</h2>
      </div>
      <div className="pj-inputs">
        <div className="gl-field">
          <label htmlFor="pj-monthly">Each month</label>
          <input id="pj-monthly" inputMode="decimal" autoComplete="off" value={monthly}
                 aria-invalid={amount == null ? 'true' : undefined}
                 aria-describedby={amount == null ? 'pj-monthly-error' : undefined}
                 onChange={(e) => setMonthly(e.target.value)}
                 onBlur={() => { if (amount != null) setMonthly(dollarsWords(amount)); }} />
          {amount == null && (
            <p className="pj-field-note" id="pj-monthly-error">Enter an amount, like $100.</p>
          )}
        </div>
        <div className="gl-field">
          <label htmlFor="pj-years">For how long</label>
          <input id="pj-years" inputMode="numeric" autoComplete="off" value={years}
                 aria-invalid={span == null ? 'true' : undefined}
                 aria-describedby={span == null ? 'pj-years-error' : undefined}
                 onChange={(e) => setYears(e.target.value)}
                 onBlur={() => { if (span != null) setYears(`${span} year${span === 1 ? '' : 's'}`); }} />
          {span == null && (
            <p className="pj-field-note" id="pj-years-error">Enter whole years, from 1 to 50.</p>
          )}
        </div>
      </div>
      {result && (
        <>
          <p className="pj-body pk-muted" aria-live="polite">
            {`You’d put in ${dollarsWords(result.putIn)}. At illustrative rates it could become:`}
          </p>
          <ul className="in-legend in-legend-dots" aria-hidden="true">
            <li><span className="in-dot in-set-aside" />What you put in</li>
            <li><span className="in-dot in-essentials" />Illustrative growth</li>
          </ul>
          <table className="pk-sr">
            <caption>What regular investing could grow to, illustrative</caption>
            <thead><tr><th scope="col">Rate</th><th scope="col">What you put in</th>
              <th scope="col">Illustrative growth</th><th scope="col">Could become</th></tr></thead>
            <tbody>
              {result.rows.map((r) => (
                <tr key={r.rate}><th scope="row">{r.label}</th><td>{dollarsWords(result.putIn)}</td>
                  <td>{dollarsWords(Math.max(r.value - result.putIn, 0))}</td><td>{dollarsWords(r.value)}</td></tr>
              ))}
            </tbody>
          </table>
          <ul className="pj-rates" aria-hidden="true">
            {result.rows.map((r) => (
              <li key={r.rate}>
                <span className="pj-rate-label">{r.label}</span>
                <span className="pj-bar">
                  <span className="pj-bar-in" style={{ width: `${(r.putInShare * 100).toFixed(2)}%` }} />
                  <span className="pj-bar-growth" style={{ width: `${(r.growthShare * 100).toFixed(2)}%` }} />
                </span>
                <span className="pj-rate-value">{dollarsWords(r.value)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="pk-label pk-muted">
        Illustrative rates of 3%, 5% and 7% a year, added monthly, before fees and taxes. Not a
        prediction or advice. Real returns go up and down and can be negative.
      </p>
      <div className="pj-calc-foot">
        <button type="button" className="in-more" onClick={onLearn}>
          Learn how fees change this<span aria-hidden="true">  ›</span>
        </button>
        {changed && result && (
          <PButton variant="secondary" className="pj-hug" onClick={onReady}>Ready to invest</PButton>
        )}
      </div>
    </section>
  );
}
