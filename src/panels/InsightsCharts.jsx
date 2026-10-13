import { useEffect, useRef, useState } from 'react';
import {
  barMonth, cash, donutArcs, monthFull, roundedTop, scaleMax, stackedAreas,
} from './insightsMath.js';

/**
 * The charts on Growth › Insights (THL-196 GR-28 to GR-32, THL-186 GR-26),
 * drawn as inline SVG in the THL-110 manner: one picture per question, each
 * with the same figures as a table for a screen reader (the SVG itself is
 * hidden from it), colours only from the tokens, and never a chart with
 * nothing in it — the callers say so in words instead.
 *
 * Essentials are --action, Lifestyle --rose, her usual --blush, money in
 * --seaglass, set aside --lilac, above usual --champagne with a gold edge.
 */

/** The width a chart has to draw in, so its text stays its own size. */
function useWidth(fallback = 560) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const measure = () => { const w = Math.floor(el.clientWidth); if (w > 0) setWidth(w); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** A visually hidden table carrying a chart's figures. */
export function ChartTable({ caption, head, rows }) {
  return (
    <table className="pk-sr">
      <caption>{caption}</caption>
      <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r[0]}>{r.map((cell, i) => (i === 0
            ? <th key={i} scope="row">{cell}</th> : <td key={i}>{cell}</td>))}</tr>
        ))}
      </tbody>
    </table>
  );
}

/** Swatches and their names under a chart. Decorative: the table says it. */
export function Legend({ items }) {
  return (
    <ul className="in-legend" aria-hidden="true">
      {items.map((i) => (
        <li key={i.label}><span className={`in-swatch ${i.tone}`} />{i.label}</li>
      ))}
    </ul>
  );
}

const PAD_TOP = 8;

/** An axis label centred under its bar, kept inside the chart at the edges. */
function AxisLabel({ x, width, height, children }) {
  const half = (String(children).length * 7) / 2;
  const anchor = x - half < 0 ? 'start' : x + half > width ? 'end' : 'middle';
  const at = anchor === 'start' ? 0 : anchor === 'end' ? width : x;
  return <text className="in-axis" x={at} y={height - 6} textAnchor={anchor}>{children}</text>;
}
const AXIS = 26;

/**
 * Essentials and Lifestyle stacked, one bar a month, over a band for her
 * usual month (GR-28's card, GR-29). `labels` puts each month's total above
 * its bar.
 */
export function TrendBars({ months, band, height = 170, labels = false, caption }) {
  const [ref, width] = useWidth();
  const top = labels ? 30 : PAD_TOP;
  const plot = height - top - AXIS;
  const max = scaleMax([...months.map((m) => m.total), band?.high ?? 0], labels ? 1.02 : 1.08);
  const slot = width / Math.max(months.length, 1);
  const bar = Math.min(labels ? 70 : 30, slot * 0.55);
  const y = (v) => top + plot - (max > 0 ? (v / max) * plot : 0);
  return (
    <figure className="in-figure">
      <ChartTable caption={caption} head={['Month', 'Essentials', 'Lifestyle', 'Total']}
                  rows={months.map((m) => [monthFull(m.month) + (m.running ? ' so far' : ''),
                                           cash(m.essentials), cash(m.lifestyle), cash(m.total)])} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          {band && (
            <rect className="in-band" x={0} width={width} y={y(band.high)}
                  height={Math.max(y(band.low) - y(band.high), 5)} />
          )}
          <line className="in-baseline" x1={0} x2={width} y1={top + plot + 0.5} y2={top + plot + 0.5} />
          {months.map((m, i) => {
            const x = slot * i + (slot - bar) / 2;
            const eh = y(0) - y(m.essentials);
            const lh = y(0) - y(m.total) - eh;
            return (
              <g key={m.month}>
                {m.lifestyle > 0 && <path className="in-lifestyle" d={roundedTop(x, y(m.total), bar, lh + 0.5)} />}
                {m.essentials > 0 && (m.lifestyle > 0
                  ? <rect className="in-essentials" x={x} y={y(m.essentials)} width={bar} height={eh} />
                  : <path className="in-essentials" d={roundedTop(x, y(m.essentials), bar, eh)} />)}
                {labels && m.total > 0 && (
                  <text className="in-value" x={x + bar / 2} y={y(m.total) - 8} textAnchor="middle">{cash(m.total)}</text>
                )}
                <AxisLabel x={slot * i + slot / 2} width={width} height={height}>
                  {barMonth(m.month, m.running)}
                </AxisLabel>
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

/**
 * Money in beside what went out (spent, with set aside on top), a pair of
 * bars a month (GR-28's card, GR-31).
 */
export function InOutBars({ rows, height = 170, caption }) {
  const [ref, width] = useWidth();
  const plot = height - PAD_TOP - AXIS;
  const max = scaleMax(rows.flatMap((r) => [r.income, r.spent + Math.max(r.set_aside, 0)]), 1.04);
  const slot = width / Math.max(rows.length, 1);
  const bar = Math.min(43, slot * 0.27);
  const y = (v) => PAD_TOP + plot - (max > 0 ? (v / max) * plot : 0);
  return (
    <figure className="in-figure">
      <ChartTable caption={caption} head={['Month', 'Money in', 'Spent', 'Set aside']}
                  rows={rows.map((r) => [monthFull(r.month) + (r.kept === null ? ' so far' : ''),
                                         r.income > 0 ? cash(r.income) : 'None',
                                         r.spent > 0 ? cash(r.spent) : 'Nothing',
                                         r.set_aside > 0 ? cash(r.set_aside) : 'Nothing'])} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          <line className="in-baseline" x1={0} x2={width} y1={PAD_TOP + plot + 0.5} y2={PAD_TOP + plot + 0.5} />
          {rows.map((r, i) => {
            const mid = slot * i + slot / 2;
            const xIn = mid - bar - 3;
            const xOut = mid + 3;
            const sa = Math.max(r.set_aside, 0);
            const spentH = y(0) - y(r.spent);
            const saH = y(0) - y(r.spent + sa) - spentH;
            return (
              <g key={r.month}>
                {r.income > 0 && <path className="in-in" d={roundedTop(xIn, y(r.income), bar, y(0) - y(r.income))} />}
                {sa > 0 && <path className="in-set-aside" d={roundedTop(xOut, y(r.spent + sa), bar, saH + 0.5)} />}
                {r.spent > 0 && (sa > 0
                  ? <rect className="in-spent" x={xOut} y={y(r.spent)} width={bar} height={spentH} />
                  : <path className="in-spent" d={roundedTop(xOut, y(r.spent), bar, spentH)} />)}
                <AxisLabel x={mid} width={width} height={height}>
                  {barMonth(r.month, r.kept === null)}
                </AxisLabel>
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

/**
 * One category's months against her usual (GR-26): a dashed line for the
 * usual month, months above it in champagne with a gold edge, never red.
 */
export function CategoryBars({ history, usual, name, height = 300 }) {
  const [ref, width] = useWidth();
  const top = 34;
  const plot = height - top - AXIS;
  const max = scaleMax([...history.map((h) => h.amount), usual ?? 0], 1.02);
  const shownWidth = Math.min(width, 640);
  const slot = shownWidth / Math.max(history.length, 1);
  const bar = Math.min(62, slot * 0.57);
  const y = (v) => top + plot - (max > 0 ? (v / max) * plot : 0);
  return (
    <figure className="in-figure">
      <ChartTable caption={`${name}, month by month${usual ? `, against a usual ${cash(usual)}` : ''}`}
                  head={['Month', 'Spent', 'Against usual']}
                  rows={history.map((h) => [monthFull(h.month) + (h.running ? ' so far' : ''),
                                            h.amount > 0 ? cash(h.amount) : 'Nothing',
                                            h.above ? 'Above usual' : 'Not above usual'])} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          {history.map((h, i) => {
            const x = slot * i + (slot - bar) / 2;
            return (
              <g key={h.month}>
                {h.amount > 0 && (
                  <>
                    <path className={h.above ? 'in-above' : 'in-essentials'}
                          d={roundedTop(x, y(h.amount), bar, y(0) - y(h.amount), 6)} />
                    <text className="in-value" x={x + bar / 2} y={y(h.amount) - 8} textAnchor="middle">
                      {cash(h.amount)}
                    </text>
                  </>
                )}
                <AxisLabel x={slot * i + slot / 2} width={width} height={height}>
                  {barMonth(h.month, h.running)}
                </AxisLabel>
              </g>
            );
          })}
          {usual > 0 && (
            <line className="in-usual-line" x1={Math.max(slot * 0.08, 0)} x2={shownWidth - slot * 0.06}
                  y1={y(usual)} y2={y(usual)} />
          )}
        </svg>
      </div>
    </figure>
  );
}

/** A ring of the month's categories, its total in the middle (GR-28, GR-30). */
export function Donut({ segments, size = 160, thickness = 32, children }) {
  const arcs = donutArcs(segments.map((s) => s.amount), { size, thickness });
  return (
    <div className="in-donut" style={{ width: size, height: size }} aria-hidden="true">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((d, i) => d && (
          <path key={segments[i].key} d={d} fillRule="evenodd"
                className={`in-${segments[i].group === 'essentials' ? 'essentials' : 'lifestyle'}`} />
        ))}
      </svg>
      <div className="in-donut-mid">{children}</div>
    </div>
  );
}

/**
 * The Anchor and each chest stacked over time (GR-32), the total traced on
 * top, and a labelled point where a chest paid for something.
 */
export function SavingsArea({ savings, height = 260, axis = 'all', labels = true }) {
  const [ref, width] = useWidth();
  const top = labels ? 40 : 10;
  const plot = height - top - AXIS;
  const keys = savings.parts.map((p) => p.key);
  const value = (pt, key) => (key === 'anchor' ? pt.anchor : pt.chests[key] ?? 0);
  const layers = keys.map((k) => savings.series.map((pt) => value(pt, k)));
  const max = scaleMax(savings.series.map((pt) => pt.total), 1.05);
  const areas = stackedAreas(layers, width, plot, max);
  const n = savings.series.length;
  const x = (i) => (n === 1 ? width / 2 : (i * width) / (n - 1));
  const yTotal = (i) => top + plot - (max > 0 ? (savings.series[i].total / max) * plot : 0);
  const line = savings.series.map((_, i) => `${x(i).toFixed(1)},${yTotal(i).toFixed(1)}`).join('L');
  const tones = ['in-essentials', 'in-lifestyle', 'in-set-aside', 'in-in', 'in-above'];
  const tone = (i) => (savings.anchor_started ? tones[i] : tones[i + 1]) ?? 'in-set-aside';
  return (
    <figure className="in-figure">
      <ChartTable caption="What your Anchor and treasure chests held at the end of each month"
                  head={['Month', ...savings.parts.map((p) => p.label), 'Together']}
                  rows={savings.series.map((pt) => [monthFull(pt.month),
                    ...keys.map((k) => (value(pt, k) > 0 ? cash(value(pt, k)) : 'Nothing')),
                    pt.total > 0 ? cash(pt.total) : 'Nothing'])} />
      {labels && savings.events.length > 0 && (
        <ul className="pk-sr">
          {savings.events.map((e) => <li key={`${e.chest}-${e.month}`}>{`${e.label} in ${monthFull(e.month)}`}</li>)}
        </ul>
      )}
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          <g transform={`translate(0 ${top})`}>
            {areas.map((a, i) => <path key={keys[i]} className={tone(i)} d={a.d} />)}
          </g>
          {n > 1 && <path className="in-total-line" d={`M${line}`} />}
          {labels && savings.events.map((e) => {
            const i = savings.series.findIndex((pt) => pt.month === e.month);
            if (i < 0) return null;
            return (
              <g key={`${e.chest}-${e.month}`}>
                <circle className="in-event" cx={x(i)} cy={yTotal(i)} r={4.5} />
                <text className="in-event-label" x={Math.min(Math.max(x(i), 60), width - 60)} y={yTotal(i) - 12}
                      textAnchor="middle">{e.label}</text>
              </g>
            );
          })}
          {savings.series.map((pt, i) => {
            const first = i === 0;
            const last = i === n - 1;
            if (axis === 'ends' && !first && !last) return null;
            return (
              <text key={pt.month} className="in-axis" x={x(i)} y={height - 6}
                    textAnchor={first ? 'start' : last ? 'end' : 'middle'}>
                {monthFull(pt.month).slice(0, 3)}
              </text>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

/** Where a month's income went, as one bar (GR-25). */
export function IncomeBar({ went, month }) {
  const parts = [
    { key: 'essentials', label: 'Essentials', value: went.essentials, tone: 'in-essentials' },
    { key: 'lifestyle', label: 'Lifestyle', value: went.lifestyle, tone: 'in-lifestyle' },
    { key: 'set_aside', label: 'Set aside', value: went.set_aside, tone: 'in-set-aside' },
    { key: 'left_over', label: 'Left over', value: went.left_over, tone: 'in-left' },
  ].filter((p) => p.value > 0);
  const total = parts.reduce((t, p) => t + p.value, 0);
  if (!total) return null;
  return (
    <figure className="in-figure">
      <ChartTable caption={`Where ${monthFull(month)}’s income went`} head={['Part', 'Amount']}
                  rows={parts.map((p) => [p.label, cash(p.value)])} />
      <div className="in-income-bar" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.key} className={p.tone} style={{ flexGrow: p.value }} />
        ))}
      </div>
      <ul className="in-legend in-legend-dots" aria-hidden="true">
        {parts.map((p) => (
          <li key={p.key}><span className={`in-dot ${p.tone}`} />{`${p.label} ${cash(p.value)}`}</li>
        ))}
      </ul>
    </figure>
  );
}
