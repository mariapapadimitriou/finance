import { useEffect, useMemo, useState } from 'react';
import { Alert, Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import { anchorWhatIf, setUnusualMonths } from '../api.js';
import {
  Line, Mark, More, PageHead, amount, listWords, monthName, monthShort, rangeWords,
} from './GoalsParts.jsx';

/**
 * When the Anchor is likely to be full (THL-132). Always a range — the best
 * and the quietest of the last three full months — and never a promise: with
 * nothing put away lately there is no date at all. A month marked unusual is
 * left out, and the explanation says which.
 */

const idx = (ym) => Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1;
const fromIdx = (i) => `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`;

/** The range band on a month axis, from this month to just past the far end. */
function RangeBand({ now, from, to }) {
  const start = idx(now);
  const months = Math.min(Math.max(idx(to) - start + 2, 6), 25);
  const axis = Array.from({ length: months }, (_, i) => fromIdx(start + i));
  const left = ((idx(from) - start) / months) * 100;
  const width = ((idx(to) - idx(from) + 1) / months) * 100;
  const every = months > 13 ? 2 : 1;
  return (
    <div className="gl-range" aria-hidden="true">
      <div className="gl-range-track">
        <span className="gl-range-band" style={{ left: `${left}%`, width: `${width}%` }} />
      </div>
      <div className="gl-range-axis">
        {axis.map((m, i) => (
          <span key={m} style={{ width: `${100 / months}%` }}>
            {i % every === 0 ? monthShort(m) : ''}
          </span>
        ))}
      </div>
    </div>
  );
}

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
      <PageHead overline="Goals · Your Anchor" title="When you’ll get there" onBack={onBack}
                backLabel="Back to your Anchor" />

      {p.state === 'range' && (
        <section className="gl-card" aria-label="Likely full">
          <p className="pk-overline">Likely full</p>
          <h2 className="pk-h1">Between {rangeWords(p.from, p.to)}</h2>
          <p className="gl-body">
            Based on what you saved in {listWords(pace.used.map((m) => monthName(m.month)))}:
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
        <section className="gl-card" aria-label="Full">
          <p className="pk-overline">Full</p>
          <h2 className="pk-h2">Your Anchor is full</h2>
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
            <div className="gl-range-track" aria-hidden="true" />
            {pace && <More onClick={onMonths}>Change which months count</More>}
          </section>
          {p.subscriptions_monthly > 0 && (
            <section className="gl-card" aria-label="One thing that could help">
              <p className="pk-overline accent">One thing that could help</p>
              <h2 className="pk-h2">Your subscriptions cost {amount(Math.round(p.subscriptions_monthly))} a month</h2>
              <p className="gl-body">Pausing one you don’t use would get your Anchor moving again.</p>
              <div className="gl-actions">
                <PButton variant="secondary" onClick={() => onTab('overview')}>See the suggestion</PButton>
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
          {amount(a.counted)} of {amount(a.target)}{a.to_go > 0 ? ` · ${amount(a.to_go)} to go` : ''}
        </p>
        <More onClick={onBack}>Back to your Anchor</More>
      </section>
    </>
  );
}

/** P-02: how the range was worked out. */
export function HowWorkedOut({ goals, onClose, onMonths }) {
  const a = goals.anchor;
  const p = a.projection;
  const pace = a.pace;
  return (
    <DetailPanel label="How we worked this out" overline="How we worked this out"
                 onClose={onClose} className="on-card">
      <h1 className="pk-h1">Your Anchor date</h1>
      <Line label="Still to go" value={amount(a.to_go)} />
      {pace && (
        <>
          <Line label="Months used" value={pace.used.map((m) => monthName(m.month)).join(', ')} />
          <Line label={`Best month · ${monthName(pace.best.month)}`}
                value={`${amount(pace.best.saved)} saved`} />
          <Line label={`Quietest month · ${monthName(pace.quietest.month)}`}
                value={pace.quietest.saved >= 0 ? `${amount(pace.quietest.saved)} saved`
                  : `${amount(-pace.quietest.saved)} taken out`} />
          <Line label="Your usual pace" value={`${amount(Math.round(pace.usual))} a month`} />
          {pace.left_out.length > 0 && (
            <Line label="Left out" value={`${leftOutWords(pace)}, marked unusual`} />
          )}
        </>
      )}
      <div className="gl-divider" />
      <Line strong label="Likely full"
            value={p?.state === 'range' ? rangeWords(p.from, p.to, 'to') : 'No date yet'} />
      <p className="pk-label pk-muted">We use your best and quietest months for the range, so
        it’s honest about ups and downs. Interest isn’t included, so you may get there a
        little sooner.</p>
      <More onClick={onMonths}>Change which months count</More>
      <div className="gl-panel-foot">
        <PButton variant="secondary" onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}

function soonerWords(n) {
  if (n == null) return '';
  if (n <= 0) return 'About the same time';
  return n === 1 ? 'About a month sooner' : `About ${n} months sooner`;
}

/** P-03: what putting aside more would do. A preview; nothing is saved. */
export function WhatIf({ goals, onClose }) {
  const usual = goals.anchor.pace?.usual ?? 0;
  const min = Math.max(10, Math.round(usual / 10) * 10);
  const max = Math.max(500, min + 100);
  const [monthly, setMonthly] = useState(Math.min(min + 50, max));
  const [result, setResult] = useState(null);

  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      anchorWhatIf(monthly).then((r) => { if (live) setResult(r); }).catch(() => {});
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [monthly]);

  const p = result?.projection;
  const extra = monthly - usual;
  const pct = ((monthly - min) / (max - min)) * 100;
  return (
    <DetailPanel label="Try a different amount" overline="Try a different amount"
                 onClose={onClose} className="on-card">
      <h1 className="pk-h1">What if you saved a bit more?</h1>
      <label className="pk-label pk-muted" htmlFor="whatif">Put aside</label>
      <p className="pk-amount" aria-hidden="true">{amount(monthly)} a month</p>
      <input id="whatif" className="gl-slider" type="range" min={min} max={max} step={10}
             value={monthly} onChange={(e) => setMonthly(Number(e.target.value))}
             style={{ '--fill': `${pct}%` }}
             aria-valuetext={`${amount(monthly)} a month`} />
      <div className="gl-line pk-label pk-muted">
        <span>{amount(min)} {usual > 0 ? 'now' : ''}</span>
        <span>{amount(max)}</span>
      </div>
      <div className="gl-note-card" role="status" aria-live="polite">
        {p?.state === 'range' ? (
          <>
            <h2 className="pk-h3">{soonerWords(result.sooner_months) || 'Likely full'}</h2>
            <p className="gl-text">Between {rangeWords(p.from, p.to)}</p>
          </>
        ) : p ? (
          <h2 className="pk-h3">Still no date at that amount</h2>
        ) : <p className="gl-text">Working it out…</p>}
        {usual > 0 && extra > 0 && (
          <p className="pk-label pk-muted">
            That’s {amount(Math.round(extra))} more a month than your usual pace.
          </p>
        )}
      </div>
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
  const months = goals.anchor.months;
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
          const said = m.saved >= 0 ? `Saved ${amount(m.saved)}` : 'More went out than came in';
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
