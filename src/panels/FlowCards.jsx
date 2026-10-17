import { useState } from 'react';
import { txAmount } from '../pearl/kit.jsx';
import './flowcards.css';

/**
 * Outflows and Inflows (ALT-04, 2026-10-17): the two cards over the list.
 *
 * Each is a figure — the month's counted flows, with its sign — and a small
 * line of how it built up day by day: solid for this month so far, ending
 * in a dot on today; dashed for an average of the three months before, the
 * whole month long. Only counted flows: spending (her share, less what a
 * chest paid) and income. Transfers, card payments and savings aren't
 * flows, so they're in neither. Hovering the line shows that day's two
 * figures. With no single month chosen ("All months") the cards are just
 * the figures.
 */

const W = 300;
const H = 80;
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "M0 80 L10 70 …": a running total as points across the month. Inflows
 *  step (pay arrives on a day); outflows slope. */
export function linePath(values, days, top, step = false) {
  if (!values?.length) return '';
  const x = (d) => (days <= 1 ? 0 : (d / (days - 1)) * W);
  const y = (v) => H - 4 - (top > 0 ? (v / top) * (H - 10) : 0);
  let d = `M${x(0).toFixed(1)} ${y(values[0]).toFixed(1)}`;
  for (let i = 1; i < values.length; i += 1) {
    if (step) d += ` H${x(i).toFixed(1)} V${y(values[i]).toFixed(1)}`;
    else d += ` L${x(i).toFixed(1)} ${y(values[i]).toFixed(1)}`;
  }
  return d;
}

/** The top of the scale: the larger of this month and the usual month, with room. */
export function scaleTop(...series) {
  const max = Math.max(0, ...series.flat().filter((v) => Number.isFinite(v)));
  return max * 1.08;
}

export function FlowChart({ kind, flows }) {
  const [hover, setHover] = useState(null);
  const now = flows[kind] ?? [];
  const usual = flows.usual?.[kind] ?? null;
  const top = scaleTop(now, usual ?? []);
  const step = kind === 'in';
  const days = flows.days;
  const last = now.length - 1;
  const at = (d) => ({ left: `${days <= 1 ? 0 : (d / (days - 1)) * 100}%`,
                       top: `${((H - 4 - (top > 0 ? ((now[d] ?? 0) / top) * (H - 10) : 0)) / H) * 100}%` });
  const pick = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const d = Math.round(((e.clientX - box.left) / box.width) * (days - 1));
    setHover(Math.max(0, Math.min(days - 1, d)));
  };
  const monthShort = SHORT[Number(flows.month.slice(5, 7)) - 1];
  return (
    <div className={`fc-chart ${kind}`} onMouseMove={pick} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
        {usual && <path className="fc-usual" d={linePath(usual, days, top, step)} vectorEffect="non-scaling-stroke" />}
        {now.length > 0 && <path className="fc-now" d={linePath(now, days, top, step)} vectorEffect="non-scaling-stroke" />}
      </svg>
      {last >= 0 && <span className="fc-dot" style={at(last)} />}
      {hover != null && (
        <>
          <span className="fc-rule" style={{ left: at(hover).left }} />
          {hover <= last && <span className="fc-dot hollow" style={at(hover)} />}
          <span className={`fc-tip${hover > days / 2 ? ' left' : ''}`} style={{ left: at(hover).left }} role="status">
            <span className="fc-tip-day">{`${monthShort} ${hover + 1}`}</span>
            {hover <= last && (
              <span className="fc-tip-row"><i className="fc-key now" />This month <b>{txAmount(now[hover])}</b></span>
            )}
            {usual && (
              <span className="fc-tip-row"><i className="fc-key usual" />{`${flows.usual.months}-month avg`} <b>{txAmount(usual[hover])}</b></span>
            )}
          </span>
        </>
      )}
    </div>
  );
}

/** Words for a screen reader: where the month stands against the usual. */
export function chartWords(kind, flows) {
  const now = flows?.[kind] ?? [];
  const usual = flows?.usual?.[kind];
  if (!now.length) return '';
  const today = now[now.length - 1];
  if (!usual) return `${txAmount(today)} so far.`;
  const then = usual[now.length - 1];
  return `${txAmount(today)} so far; usually ${txAmount(then)} by now.`;
}

export default function FlowCards({ totals, flows }) {
  if (!totals) return null;
  const card = (kind, label, value, tone) => (
    <section className={`fc-card ${kind}`} aria-label={label}>
      <p className="fc-label">{label}</p>
      <p className={`fc-figure ${tone}`}>{value}</p>
      {flows && <span className="pk-sr">{chartWords(kind, flows)}</span>}
      {flows && <FlowChart kind={kind} flows={flows} />}
    </section>
  );
  return (
    <div className="fc-cards">
      {card('out', 'Outflows', txAmount(totals.spent, { signed: totals.spent >= 0.005 }), 'out')}
      {card('in', 'Inflows', txAmount(totals.income, { inflow: totals.income >= 0.005 }), 'in')}
    </div>
  );
}
