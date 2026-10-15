import { useMemo, useState } from 'react';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { RangeBand, Slider } from '../pearl/viz.jsx';
import {
  addMonths, monthsTo, sliderBounds, sliderWords, soonerWords, whatIf,
} from '../pearl/vizMath.js';
import { money, setUnusualMonths } from '../api.js';
import { writeInsightsUrl } from '../router.js';
import {
  Mark, More, PageHead, amount, listWords, monthName, monthYear, rangeWords,
} from './GoalsParts.jsx';
import { Ledger } from './HomePanel.jsx';
import './home.css';

/**
 * When the Anchor is likely to cover three months of Essentials (THL-132,
 * THL-230). Always a range — the best and the quietest of the last three
 * full months, each what the Anchor grew by: put away, less what the chests
 * took — and never a promise: with nothing put away lately there is no date
 * at all. A month marked unusual is left out, and the explanation says which.
 */

function leftOutWords(pace) {
  const names = (pace?.left_out ?? []).map((m) => monthName(m.month));
  return names.length ? listWords(names) : '';
}

/** P-01 and P-05: the projection page. */
export function ProjectionPage({ goals, onBack, onHow, onWhatIf, onMonths, onTab }) {
  const a = goals.anchor;
  const p = a.projection ?? { state: 'none', reason: 'no_history' };
  const pace = a.pace;
  const leftOut = pace?.left_out ?? [];
  return (
    <>
      <PageHead overline="Save · Your Anchor" title="When you’ll reach 3 months" onBack={onBack}
                backLabel="Back to your Anchor" />

      {p.state === 'range' && (
        <section className="gl-card" aria-label="Likely there">
          <p className="pk-overline">Likely there</p>
          <h2 className="pk-h1">Between {rangeWords(p.from, p.to)}</h2>
          <p className="gl-body">
            {a.chests_monthly > 0
              ? `Your Anchor grows by what you put away, less the ${amount(a.chests_monthly)} a month your chests take.`
              : 'Your Anchor grows by what you put away.'}
            {' '}From {listWords(pace.used.map((m) => monthName(m.month)))}:
            {' '}{amount(p.low)} to {amount(p.high)} a month. Interest isn’t included.
          </p>
          <RangeBand now={goals.month} from={p.from} to={p.to} />
          <span className="pk-sr">The range runs from {rangeWords(p.from, p.to, 'to')}.</span>
          <div className="gl-links">
            <More onClick={onHow}>How we worked this out</More>
            <More onClick={onWhatIf}>Try a different amount</More>
          </div>
        </section>
      )}

      {p.state === 'full' && (
        <section className="gl-card" aria-label="Milestone reached">
          <p className="pk-overline">Milestone reached</p>
          <h2 className="pk-h2">Your Anchor covers 3 months</h2>
          <p className="gl-body">There’s nothing left to project. Keep it topped up and it’ll
            keep you steady.</p>
        </section>
      )}

      {p.state === 'none' && (
        <>
          <section className="gl-card" aria-label="No date yet">
            <p className="pk-overline">No date yet</p>
            <h2 className="pk-h2">
              {p.reason === 'no_pace' ? 'Lately, more has gone out than come in'
                : 'Not enough saving to go on yet'}
            </h2>
            <p className="gl-body">
              {p.reason === 'no_pace'
                ? 'A date wouldn’t be honest right now. As soon as you save a little, we’ll show a range again.'
                : 'Once a full month with money moved to savings is in, we’ll show a range.'}
            </p>
            <RangeBand now={goals.month} />
            {pace && <More onClick={onMonths}>Change which months count</More>}
          </section>
          {p.subscriptions_monthly > 0 && (
            <section className="gl-card" aria-label="One thing that could help">
              <p className="pk-overline accent">One thing that could help</p>
              <h2 className="pk-h2">Your subscriptions cost {amount(Math.round(p.subscriptions_monthly))} a month</h2>
              <p className="gl-body">Pausing one you don’t use would get your Anchor moving again.</p>
              <div className="gl-actions">
                <PButton variant="secondary" onClick={() => {
                  // Growth › Insights › Your subscriptions (GR-27).
                  writeInsightsUrl({ view: 'subscriptions' });
                  onTab('insights');
                }}>See the suggestion</PButton>
              </div>
            </section>
          )}
        </>
      )}

      {p.state === 'range' && leftOut.length > 0 && (
        <Alert action="Change" onAction={onMonths}>
          {leftOut.length === 1 ? '1 month' : `${leftOut.length} months`} left out: you marked
          {' '}{leftOutWords(pace)} as unusual, so {leftOut.length === 1 ? 'it isn’t' : 'they aren’t'}
          {' '}part of your pace.
        </Alert>
      )}

      <section className="gl-card gl-row-card gl-mini" aria-label="Your Anchor">
        <Mark phase={a.earned ? 'unveil' : 'build'} width={40} />
        <p className="gl-text gl-grow">
          {a.target > 0 ? `${amount(a.counted)} of ${amount(a.target)}` : amount(a.counted)}
          {a.to_go > 0 ? ` · ${amount(a.to_go)} to go` : ''}
        </p>
        <More onClick={onBack}>Back to your Anchor</More>
      </section>
    </>
  );
}

const cents = (n) => money(n, { cents: true });

/** "July 2027 to June 2028", or one month when that's all. */
function likelyWords(p) {
  if (p?.state !== 'range') return 'No date yet';
  return p.from === p.to ? monthYear(p.from) : rangeWords(p.from, p.to, 'to');
}

/** "+$360 to your Anchor", or "$120 out of it". */
const grew = (m) => (m.saved >= 0 ? `+${amount(m.saved)} to your Anchor` : `${amount(-m.saved)} out of it`);

/**
 * P-02's sheet: still to go, the months used, the best and quietest of
 * them (what the Anchor grew by: put away, less what the chests took), her
 * usual pace, what was left out, and the range.
 */
export function rangeSheet(goals) {
  const a = goals.anchor;
  const p = a.projection;
  const pace = a.pace;
  const used = pace.used.map((m) => monthName(m.month));
  const rows = [
    { key: 'to_go', label: 'Still to go', display: amount(a.to_go), lines: [] },
    { key: 'months', label: 'Months used', display: used.join(', '), lines: [] },
    { key: 'best', label: `Best month · ${monthName(pace.best.month)}`, display: grew(pace.best),
      lines: [] },
    { key: 'quietest', label: `Quietest month · ${monthName(pace.quietest.month)}`,
      display: grew(pace.quietest), lines: [] },
    { key: 'usual', label: 'Your usual pace', display: `${amount(pace.usual)} a month`,
      lines: pace.used.map((m) => ({ label: monthName(m.month), display: grew(m) })) },
  ];
  if (pace.left_out.length) {
    rows.push({ key: 'left_out', label: 'Left out',
                display: `${listWords(pace.left_out.map((m) => monthName(m.month)))}, marked unusual`,
                lines: pace.left_out.map((m) => ({ label: monthName(m.month), display: grew(m) })) });
  }
  const total = { label: 'Likely there', display: likelyWords(p),
                  detail: monthsTo(a.to_go, pace.usual) == null ? null
                    : `About ${monthsTo(a.to_go, pace.usual)} months at your usual pace, from ${monthName(addMonths(goals.month, 1))}` };
  const note = 'We use your best and quietest months for the range, so it’s honest about ups and '
    + 'downs. Interest isn’t included, so you may get there a little sooner.';
  return { title: 'Your Anchor date', rows, total, note };
}

/** P-02, laid out as X-03: how the range was worked out. */
export function HowWorkedOut({ goals, onClose, onWhatIf, onMonths }) {
  if (!goals.anchor.pace) return null;
  const { title, rows, total, note } = rangeSheet(goals);
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} sheet className="hm-sheet">
      <h1 className="pk-h2">{title}</h1>
      <Ledger rows={rows} total={total} />
      <p className="pk-muted hm-note">{note}</p>
      <button type="button" className="hm-link" onClick={onWhatIf}>
        Want it sooner? Try a different monthly amount
      </button>
      <button type="button" className="hm-link" onClick={onMonths}>Change which months count</button>
      <div className="hm-sheet-foot">
        <PButton onClick={onClose}>Got it</PButton>
      </div>
    </DetailPanel>
  );
}

/**
 * P-03: what putting aside more would do. A preview; nothing is saved. The
 * projection is worked out here on the device (vizMath.whatIf, a port of
 * finance/anchor.py), so it follows the slider instantly.
 */
export function WhatIf({ goals, onClose, initial = null }) {
  const a = goals.anchor;
  const usual = a.pace?.usual ?? 0;
  const bounds = sliderBounds(usual);
  // A recommendation's "Try it" (THL-12) opens on the amount it suggested.
  const [monthly, setMonthly] = useState(() => (
    bounds && initial !== null ? Math.min(Math.max(initial, bounds.min), bounds.max) : bounds?.start ?? 0));
  const result = bounds ? whatIf({
    toGo: a.to_go, pace: a.pace, now: goals.month, current: a.projection,
  }, monthly) : null;

  const p = result?.projection;
  const extra = monthly - usual;
  return (
    <DetailPanel label="Try a different amount" overline="Try a different amount"
                 onClose={onClose} className="on-card">
      <h1 className="pk-h1">What if you saved a bit more?</h1>
      {bounds ? (
        <>
          <label className="pk-label pk-muted" htmlFor="whatif">Put aside</label>
          <p className="pk-amount" aria-hidden="true">{amount(monthly)} a month</p>
          <Slider id="whatif" value={monthly} bounds={bounds} onChange={setMonthly}
                  valueText={sliderWords(monthly, result)} />
          <div className="gl-line pk-label pk-muted">
            <span>{amount(bounds.min)} now</span>
            <span>{amount(bounds.max)}</span>
          </div>
          <div className="gl-note-card" role="status" aria-live="polite">
            {p?.state === 'range' ? (
              <>
                <h2 className="pk-h3">{soonerWords(result.sooner) || 'Likely there'}</h2>
                <p className="gl-text">Between {rangeWords(p.from, p.to)}</p>
              </>
            ) : <h2 className="pk-h3">Still no date at that amount</h2>}
            {extra > 0 && (
              <p className="pk-label pk-muted">
                That’s {amount(Math.round(extra))} more a month than your usual pace.
              </p>
            )}
          </div>
        </>
      ) : (
        <p className="gl-body">Once you’ve put a little aside for a month, you can try
          different amounts here.</p>
      )}
      <p className="pk-label pk-muted">This is only a preview. Nothing changes until you move
        more money.</p>
      <div className="gl-panel-foot">
        <PButton onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

/** P-04: leave out an unusual month. */
export function UnusualMonths({ goals, onClose, onDone }) {
  const months = goals.anchor.pace_months ?? [];
  const [picked, setPicked] = useState(() => new Set(goals.anchor.unusual));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // The last four full months, and any older one already left out.
  const shown = useMemo(() => months.filter((m, i) => i < 4 || picked.has(m.month)),
    [months, picked]);
  const count = shown.filter((m) => picked.has(m.month)).length;
  return (
    <DetailPanel label="Which months count" overline="Which months count" onClose={onClose}
                 className="on-card">
      <h1 className="pk-h1">Leave out an unusual month</h1>
      <p className="gl-body">If a month won’t happen again, like a car repair or a move, tick
        it and we’ll work out your pace without it.</p>
      {shown.length === 0 && (
        <p className="gl-body">There isn’t a full month to choose from yet.</p>
      )}
      <div className="pk-choices">
        {shown.map((m) => {
          const on = picked.has(m.month);
          const said = m.saved >= 0 ? `Put away ${amount(m.saved)}` : 'More went out than came in';
          return (
            <Choice key={m.month} type="checkbox" checked={on} label={monthName(m.month)}
                    description={on ? `${said} · left out` : said}
                    onChange={(v) => setPicked((s) => {
                      const next = new Set(s);
                      if (v) next.add(m.month); else next.delete(m.month);
                      return next;
                    })} />
          );
        })}
      </div>
      {count > 0 && (
        <Alert>{count === 1 ? '1 month' : `${count} months`} left out. The more months you
          leave out, the more hopeful the date gets.</Alert>
      )}
      {error && <p className="txd-hint" role="alert">{error}</p>}
      <div className="gl-panel-foot">
        <PButton disabled={busy} onClick={async () => {
          setBusy(true); setError('');
          try { onDone(await setUnusualMonths([...picked])); onClose(); }
          catch (e) { setError(e.message); }
          finally { setBusy(false); }
        }}>{busy ? 'Saving…' : 'Done'}</PButton>
      </div>
    </DetailPanel>
  );
}
