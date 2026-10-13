import { useState } from 'react';
import { putHomeView, setSavingPace } from '../api.js';
import { DetailPanel, PButton, Toast } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { Slider } from '../pearl/viz.jsx';
import { ForecastChart, Next30Chart, SavingsChart } from './ProjectionsCharts.jsx';
import { monthFull } from './insightsMath.js';
import {
  cash, comingUp, extraBounds, forecastParts, forecastSentence, monthYear, next30Line, rangeWords,
  savingsAt, savingsWords,
} from './projectionsMath.js';

/**
 * The detail views behind Growth › Projections (ProjectionsPanel.jsx), each
 * at its own address under /growth/projections:
 *
 * GR-34 (THL-191) /forecast  Where the month is heading: spending so far, the
 *                            likely range to the month's end as a wedge, and
 *                            the "what you can spend" line.
 * GR-35 (THL-192) /next30    The expected balance, paydays and bills on one
 *                            timeline, and Coming up. A bill she hasn't
 *                            confirmed is dashed and says so.
 * GR-36 (THL-194) /savings   Savings in a year at her current pace, and with
 *                            a little more (the THL-57 slider).
 */

/** "‹ Projections", the overline and the title every detail view opens with. */
function DetailHead({ nav, title }) {
  return (
    <header className="in-detail-head">
      <div className="in-back-row">
        <button type="button" className="in-back" onClick={() => nav.show('')}>
          <PIcon name="chevronRight" size={12} className="in-flip" /> Projections
        </button>
      </div>
      <div className="hm-head">
        <p className="pk-overline accent">Projections</p>
        <h1 className="pk-h1">{title}</h1>
      </div>
    </header>
  );
}

function Parts({ title, rows, note, onClose }) {
  return (
    <DetailPanel label={title} overline="How we worked this out" onClose={onClose} className="on-card">
      <h1 className="pk-h1">{title}</h1>
      <dl className="pj-parts">
        {rows.map((r) => (
          <div key={r.label} className={r.strong ? 'strong' : undefined}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      {note && <p className="pk-label pk-muted">{note}</p>}
      <div className="gl-panel-foot">
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

// ── GR-34 This month ──────────────────────────────────────────────────────

export function ForecastView({ d, nav }) {
  const f = d.forecast;
  const [how, setHow] = useState(false);
  const week = () => {
    putHomeView('week').catch(() => {});
    nav.onTab?.('home');
  };
  const afford = () => {
    // Home's "Can I afford it?" (THL-167) sits under the week.
    putHomeView('week').catch(() => {});
    nav.onTab?.('home');
    setTimeout(() => {
      const input = document.getElementById('hm-afford-amount');
      input?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      input?.focus({ preventScroll: true });
    }, 600);
  };
  return (
    <div className="pk hm-page in-page pj-page">
      <DetailHead nav={nav} title={`Where ${monthFull(f.month)} is heading`} />
      <section className="hm-card in-card" aria-label="This month">
        <p className="pj-body">{forecastSentence(f)}</p>
        {f.state !== 'none' && <ForecastChart f={f} full height={300} />}
        {f.state !== 'none' && (
          <button type="button" className="in-more pj-how" onClick={() => setHow(true)}>
            How we worked this out<span aria-hidden="true">  ›</span>
          </button>
        )}
      </section>
      <div className="in-actions">
        <PButton variant="secondary" onClick={week}>See this week</PButton>
        <button type="button" className="in-text-btn" onClick={afford}>Can I afford it?</button>
      </div>
      {how && (
        <Parts title="Where the month is heading" rows={forecastParts(f)} onClose={() => setHow(false)}
               note="The rest of the month runs from your quietest month to your busiest after this day of it, bills left out because they’re counted by name. Months you marked unusual are left out." />
      )}
    </div>
  );
}

// ── GR-35 The next 30 days ────────────────────────────────────────────────

export function Next30View({ d, nav }) {
  const n = d.next30;
  const rows = comingUp(n);
  return (
    <div className="pk hm-page in-page pj-page">
      <DetailHead nav={nav} title="The next 30 days" />
      <section className="hm-card in-card" aria-label="The next 30 days">
        <p className="pj-body">{next30Line(n, { long: true })}</p>
        {(n.series.length > 0 || rows.length > 0) && <Next30Chart n={n} full height={300} />}
      </section>
      <section className="hm-card in-card" aria-labelledby="pj-coming-title">
        <h2 className="pk-h3" id="pj-coming-title">Coming up</h2>
        {rows.length ? (
          <ul className="pj-coming">
            {rows.map((e) => (
              <li key={`${e.date}-${e.kind}-${e.label}`}>
                <span className={`pj-dot ${e.kind === 'payday' ? 'payday' : 'bill'}${e.unconfirmed ? ' unconfirmed' : ''}`}
                      aria-hidden="true" />
                <span className="pj-day">{e.day}</span>
                <span className="in-grow">
                  {e.name}{e.unconfirmed && <span className="pk-muted">{' · not confirmed yet'}</span>}
                </span>
                <span className="in-num">{e.value}</span>
                {e.unconfirmed && (
                  <button type="button" className="in-more" onClick={() => nav.onTab?.('income')}
                          aria-label={`Confirm ${e.name}`}>
                    Confirm<span aria-hidden="true">  ›</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="pk-muted">No paydays or bills in the next 30 days that we know of. Add them in
            Profile › Income and bills.</p>
        )}
      </section>
    </div>
  );
}

// ── GR-36 Savings in a year ───────────────────────────────────────────────

export function SavingsView({ d, nav }) {
  const s = d.savings;
  const bounds = extraBounds(s);
  const [extra, setExtra] = useState(Math.min(50, bounds.max));
  const [how, setHow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const words = savingsWords(s, extra);
  const usual = s.pace ? s.pace.usual / 100 : 0;
  const pace = Math.round(usual + extra);
  const anchorStarted = d.anchor?.state !== 'not_started';
  const use = async () => {
    setBusy(true);
    try {
      const next = await setSavingPace(pace);
      nav.setData(next);
      setDone(`You’ll set aside ${cash(pace * 100)} a month`);
      nav.onChanged?.();
    } finally {
      setBusy(false);
    }
  };
  const more = extra > 0 ? savingsAt(s, extra) : null;
  return (
    <div className="pk hm-page in-page pj-page">
      <DetailHead nav={nav} title="Your savings in a year" />
      <section className="hm-card in-card" aria-label="Your savings in a year">
        <p className="pj-body" aria-live="polite">{words.sentence}</p>
        <SavingsChart s={s} extra={extra} full height={300} />
        <div className="pj-slider-row">
          <label className="pj-slider-label" htmlFor="pj-extra">Save a bit more</label>
          <Slider id="pj-extra" value={extra} bounds={bounds} onChange={setExtra}
                  valueText={more ? `${cash(extra * 100)} more a month, ${rangeWords(more)} by ${monthYear(s.by)}`
                    : 'Nothing more a month'} />
          <span className="pj-slider-value" aria-hidden="true">
            {extra > 0 ? `+${cash(extra * 100)} a month` : 'Nothing more'}
          </span>
        </div>
        <p className="pk-label pk-muted">A range, not a promise. It moves as your months change.</p>
      </section>
      <div className="in-actions">
        {pace > 0 && (
          <PButton variant="secondary" disabled={busy} onClick={use}>
            {anchorStarted ? 'Use this pace for my Anchor' : 'Use this pace for my saving goal'}
          </PButton>
        )}
        <button type="button" className="in-text-btn" onClick={() => setHow(true)}>How we worked this out</button>
      </div>
      {how && (
        <Parts title="Your savings in a year" onClose={() => setHow(false)}
               rows={[
                 { label: 'In your Anchor and chests now', value: s.now > 0 ? cash(s.now) : 'Nothing yet' },
                 ...(s.pace ? [
                   { label: `Your months, ${s.pace.months.map(monthFull).join(', ')}`,
                     value: `${rangeWords(s.pace)} a month` },
                 ] : []),
                 ...(s.state === 'ok' ? [{ label: `Likely by ${monthYear(s.by)}`, value: rangeWords(savingsAt(s, 0)),
                                           strong: true }] : []),
                 ...(more ? [{ label: `With ${cash(extra * 100)} more a month`, value: rangeWords(more) }] : []),
               ]}
               note="Twelve months at your quietest month’s pace to your best. Interest isn’t included, and a chest that opens spends what it holds." />
      )}
      {done && <Toast onDone={() => setDone(null)}>{done}</Toast>}
    </div>
  );
}
