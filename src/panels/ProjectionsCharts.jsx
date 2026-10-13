import { ChartTable, Legend, useWidth } from './InsightsCharts.jsx';
import { dayLong, dayShort, monthFull, monthShort } from './insightsMath.js';
import { cash, comingUp, monthTick, monthYear, rangeWords, savingsAt } from './projectionsMath.js';

/**
 * The pictures on Growth › Projections (THL-197 GR-33 to GR-36), drawn as
 * inline SVG the way Insights draws its charts (THL-110): each says its
 * figures again in a table for a screen reader, and the SVG itself is
 * hidden from it. A projection is always a wedge — a range — never a line.
 *
 * Spent so far and the expected balance are --action, the likely range
 * --blush, a what-if --lilac, paydays --seaglass, bills --champagne with a
 * gold edge (dashed while she hasn't confirmed one), what she can spend a
 * dashed ink line. No red anywhere.
 *
 * `full` draws the detail view's labels; without it the card on the page
 * gets the same picture, quieter.
 */

const pts = (list) => list.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
const linePath = (list) => list.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');

/** Text kept inside the chart at its edges. */
function Label({ x, y, width, children, className = 'in-axis', anchor = 'middle' }) {
  const half = (String(children).length * 7) / 2;
  let a = anchor;
  if (a === 'middle') a = x - half < 0 ? 'start' : x + half > width ? 'end' : 'middle';
  const at = a === 'start' && anchor === 'middle' ? Math.max(x, 0)
    : a === 'end' && anchor === 'middle' ? Math.min(x, width) : x;
  return <text className={className} x={at} y={y} textAnchor={a}>{children}</text>;
}

// ── This month (GR-34) ────────────────────────────────────────────────────

export function ForecastChart({ f, height = 130, full = false }) {
  const [ref, width] = useWidth();
  const right = full ? 76 : 0;
  const top = full ? 28 : 10;
  const bottom = full ? 30 : 4;
  const plotW = Math.max(width - right, 40);
  const base = height - bottom;
  const days = f.days_in_month;
  const last = f.line[f.line.length - 1] ?? { day: f.day, spent: f.spent };
  const max = Math.max(f.can_spend ?? 0, f.spend.high, last.spent, 1) * 1.04;
  const x = (d) => ((d - 1) / Math.max(days - 1, 1)) * plotW;
  const y = (v) => top + (base - top) * (1 - Math.max(v, 0) / max);
  const now = [x(last.day), y(last.spent)];
  const end = x(days);
  const mid = (f.spend.low + f.spend.high) / 2;
  const ticks = [1, 8, 15, 22, days];
  const bills = f.bills_ahead ?? [];
  const name = monthFull(f.month);
  return (
    <figure className="in-figure pj-figure">
      <ChartTable caption={`${name}: spent so far and where it’s likely to end`}
                  head={['', 'Amount']}
                  rows={[
                    [`Spent by ${dayLong(`${f.month}-${String(last.day).padStart(2, '0')}`)}`,
                     last.spent > 0 ? cash(last.spent) : 'Nothing yet'],
                    ...bills.map((b) => [`${b.label}, due ${dayLong(b.date)}${b.confirmed ? '' : ', not confirmed yet'}`,
                                         cash(b.amount)]),
                    ['Likely spent by the end of the month', rangeWords(f.spend)],
                    ...(f.can_spend != null ? [['What you can spend this month', cash(f.can_spend)]] : []),
                  ]} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          <line className="in-baseline" x1={0} x2={plotW} y1={base + 0.5} y2={base + 0.5} />
          {f.can_spend != null && f.can_spend > 0 && (
            <>
              <line className="pj-limit" x1={0} x2={plotW} y1={y(f.can_spend)} y2={y(f.can_spend)} />
              {full && (
                <text className="pj-note" x={0} y={y(f.can_spend) - 8}>
                  {`What you can spend this month: ${cash(f.can_spend)}`}
                </text>
              )}
            </>
          )}
          {last.day < days && (
            <>
              <polygon className="pj-wedge" points={pts([now, [end, y(f.spend.high)], [end, y(f.spend.low)]])} />
              <line className="pj-dash" x1={now[0]} y1={now[1]} x2={end} y2={y(mid)} />
            </>
          )}
          {full && (
            <line className="pj-today" x1={now[0]} x2={now[0]} y1={top - 10} y2={base} />
          )}
          <path className="pj-line" d={linePath([[x(1), y(0)], ...f.line.map((p) => [x(p.day), y(p.spent)])])} />
          <circle className="pj-point" cx={now[0]} cy={now[1]} r={4} />
          {full && (
            <Label x={now[0] + 8} y={now[1] + 22} width={plotW} className="pj-note" anchor="start">
              {`Today · ${cash(last.spent)}`}
            </Label>
          )}
          {full && last.day < days && (
            <>
              <text className="pj-end" x={plotW + 12} y={y(f.spend.high) + 4}>{cash(f.spend.high)}</text>
              {f.spend.low !== f.spend.high && (
                <text className="pj-end" x={plotW + 12} y={Math.max(y(f.spend.low) + 4, y(f.spend.high) + 22)}>
                  {cash(f.spend.low)}
                </text>
              )}
            </>
          )}
          {full && bills.map((b, i) => {
            const bx = x(Number(b.date.slice(8, 10)));
            return (
              <g key={`${b.date}-${b.label}`}>
                <circle className={`pj-bill${b.confirmed ? '' : ' unconfirmed'}`} cx={bx} cy={base} r={5} />
                <Label x={bx} y={base - 12 - (i % 2) * 16} width={plotW} className="pj-note">
                  {`${b.label} ${cash(b.amount)}`}
                </Label>
              </g>
            );
          })}
          {full && ticks.map((d) => (
            <Label key={d} x={x(d)} y={height - 6} width={plotW}>{`${monthShort(f.month)} ${d}`}</Label>
          ))}
        </svg>
      </div>
      {full && (
        <Legend items={[
          { label: 'Spent so far', tone: 'in-essentials' },
          { label: 'Likely range', tone: 'in-band' },
          ...(f.can_spend != null ? [{ label: 'What you can spend', tone: 'pj-swatch-limit' }] : []),
          ...(bills.length ? [{ label: 'Bill still to come', tone: 'in-above' }] : []),
        ]} />
      )}
    </figure>
  );
}

// ── The next 30 days (GR-35) ──────────────────────────────────────────────

const dayIndex = (start, iso) => Math.round((Date.parse(iso) - Date.parse(start)) / 86400000);

const textWidth = (text) => String(text).length * 7;

/**
 * Where each event's label goes: paydays above the axis, bills in two rows
 * below it, the biggest placed first. A label with no room is left off —
 * the list under the chart and the table name every one.
 */
function placeLabels(events, x, width) {
  const rows = { above: [[]], below: [[], []] };
  const out = new Map();
  const order = [...events].sort((a, b) => (a.kind === 'payday' ? -1 : 0) - (b.kind === 'payday' ? -1 : 0)
    || b.amount - a.amount);
  for (const e of order) {
    const text = `${e.kind === 'payday' ? 'Payday' : e.label} ${cash(e.amount)}`;
    const w = textWidth(text);
    const cx = Math.min(Math.max(x(e), w / 2), width - w / 2);
    const span = [cx - w / 2 - 6, cx + w / 2 + 6];
    const side = e.kind === 'payday' ? 'above' : 'below';
    const row = rows[side].findIndex((taken) => taken.every(([a, b]) => span[1] < a || span[0] > b));
    if (row < 0) continue;
    rows[side][row].push(span);
    out.set(e, { text, row, side });
  }
  return out;
}

export function Next30Chart({ n, height = 100, full = false }) {
  const [ref, width] = useWidth();
  const hasLine = n.series.length > 0;
  const axisY = full ? height - 92 : height - 12;
  const top = full ? 36 : 8;
  const lineBottom = axisY - (full ? 70 : 28);
  const plotW = Math.max(width, 40);
  const x = (i) => (i / n.days) * plotW;
  const values = n.series.map((s) => s.balance);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const y = (v) => top + (lineBottom - top) * (1 - (v - lo) / Math.max(hi - lo, 1));
  const low = n.lowest && dayIndex(n.start, n.lowest.date);
  const rows = comingUp(n);
  const ex = (e) => x(dayIndex(n.start, e.date));
  const labels = full ? placeLabels(n.events, ex, plotW) : new Map();
  // Bills first, so a payday on the same day sits on top of them.
  const drawn = [...n.events].sort((a, b) => (a.kind === 'payday') - (b.kind === 'payday'));
  const unconfirmed = n.events.some((e) => e.kind === 'bill' && !e.confirmed);
  return (
    <figure className="in-figure pj-figure">
      <ChartTable caption="The next 30 days: paydays, bills and the expected balance"
                  head={['Date', 'What', 'Amount', ...(hasLine ? ['Expected balance after'] : [])]}
                  rows={rows.map((e) => {
                    const after = n.series.find((s) => s.date === e.date);
                    return [`${dayLong(e.date)} · ${e.name}${e.unconfirmed ? ' (not confirmed yet)' : ''}`,
                            e.kind === 'payday' ? `Payday, ${e.label}` : 'Bill',
                            e.value, ...(hasLine ? [after && after.balance > 0 ? `about ${cash(after.balance)}` : 'close to empty'] : [])];
                  })} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          {hasLine && (
            <>
              <path className="pj-line" d={linePath(n.series.map((s, i) => [x(i), y(s.balance)]))} />
              {n.lowest && (
                <>
                  <circle className="pj-point" cx={x(low)} cy={y(n.series[low].balance)} r={4} />
                  {full && (
                    <Label x={x(low)} y={y(n.series[low].balance) + 24} width={plotW} className="pj-note">
                      {n.lowest.amount > 0 ? `Lowest: about ${cash(n.lowest.amount)}` : 'Lowest: close to empty'}
                    </Label>
                  )}
                </>
              )}
            </>
          )}
          <line className="pj-axis" x1={0} x2={plotW} y1={axisY} y2={axisY} />
          {drawn.map((e) => {
            const payday = e.kind === 'payday';
            const label = labels.get(e);
            const ly = payday ? axisY - 14 : axisY + 26 + (label?.row ?? 0) * 22;
            return (
              <g key={`${e.date}-${e.kind}-${e.label}`}>
                <circle className={payday ? 'pj-payday' : `pj-bill${e.confirmed ? '' : ' unconfirmed'}`}
                        cx={ex(e)} cy={axisY} r={payday ? 7 : 6} />
                {label && (
                  <Label x={ex(e)} y={ly} width={plotW} className={payday ? 'pj-note strong' : 'pj-note'}>
                    {label.text}
                  </Label>
                )}
              </g>
            );
          })}
          {full && [0, 7, 14, 21, n.days].map((i) => {
            const iso = new Date(Date.parse(n.start) + i * 86400000).toISOString().slice(0, 10);
            return <Label key={i} x={x(i)} y={height - 6} width={plotW}>{dayShort(iso)}</Label>;
          })}
        </svg>
      </div>
      {full && (
        <Legend items={[
          ...(hasLine ? [{ label: 'Expected balance', tone: 'in-essentials' }] : []),
          { label: 'Payday', tone: 'in-in' },
          { label: 'Bill', tone: 'in-above' },
          ...(unconfirmed ? [{ label: 'Bill not confirmed yet', tone: 'pj-swatch-unconfirmed' }] : []),
        ]} />
      )}
    </figure>
  );
}

// ── Savings in a year (GR-36) ─────────────────────────────────────────────

const nextMonth = (ym, k) => {
  const t = Number(ym.slice(0, 4)) * 12 + Number(ym.slice(5, 7)) - 1 + k;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
};

export function SavingsChart({ s, extra = 0, height = 74, full = false }) {
  const [ref, width] = useWidth();
  const right = full ? 150 : 0;
  const top = full ? 24 : 6;
  const bottom = full ? 30 : 4;
  const plotW = Math.max(width - right, 40);
  const base = height - bottom;
  const history = s.history.length ? s.history : [{ month: s.month, total: s.now }];
  const months = [...history.map((h) => h.month), ...Array.from({ length: 12 }, (_, k) => nextMonth(s.month, k + 1))];
  const nowAt = history.length - 1;
  const cur = savingsAt(s, 0);
  const more = extra > 0 ? savingsAt(s, extra) : null;
  const max = Math.max(cur.high, more?.high ?? 0, ...history.map((h) => h.total), 1) * 1.04;
  const x = (i) => (i / Math.max(months.length - 1, 1)) * plotW;
  const y = (v) => top + (base - top) * (1 - Math.max(v, 0) / max);
  const now = [x(nowAt), y(s.now)];
  const end = x(months.length - 1);
  const ticks = months.map((m, i) => ({ m, i })).filter(({ i }) => (i - nowAt) % 3 === 0 || i === months.length - 1);
  return (
    <figure className="in-figure pj-figure">
      <ChartTable caption="Your savings: so far, and likely in a year"
                  head={['', 'Amount']}
                  rows={[
                    ...history.map((h) => [`End of ${monthYear(h.month)}${h.month === s.month ? ' so far' : ''}`,
                                           h.total > 0 ? cash(h.total) : 'Nothing yet']),
                    [`Likely by ${monthYear(s.by)}, at your current pace`, s.state === 'ok' ? rangeWords(cur) : 'No range yet'],
                    ...(more ? [[`With ${cash(extra * 100)} more a month`, rangeWords(more)]] : []),
                  ]} />
      <div ref={ref} className="in-chart" aria-hidden="true">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          <line className="in-baseline" x1={0} x2={plotW} y1={base + 0.5} y2={base + 0.5} />
          {more && <polygon className="pj-wedge-more" points={pts([now, [end, y(more.high)], [end, y(more.low)]])} />}
          {(s.state === 'ok' || more) && (
            <polygon className="pj-wedge" points={pts([now, [end, y(cur.high)], [end, y(cur.low)]])} />
          )}
          {full && s.opens.map((o) => {
            const i = months.indexOf(o.month);
            if (i < 0) return null;
            return (
              <g key={`${o.month}-${o.label}`}>
                <line className="pj-today" x1={x(i)} x2={x(i)} y1={top - 6} y2={base} />
                <Label x={x(i) + 6} y={top + 4} width={plotW} className="pj-note" anchor="start">{o.label}</Label>
              </g>
            );
          })}
          <path className="pj-line" d={linePath(history.map((h, i) => [x(i), y(h.total)]))} />
          <circle className="pj-point" cx={now[0]} cy={now[1]} r={4} />
          {full && more && (
            <text className="pj-end" x={plotW + 12} y={y(more.high) + 4}>{rangeWords(more)}</text>
          )}
          {full && s.state === 'ok' && (
            <text className="pj-end" x={plotW + 12}
                  y={more ? Math.max(y(cur.high) + 4, y(more.high) + 30) : y(cur.high) + 4}>
              {rangeWords(cur)}
            </text>
          )}
          {full && ticks.map(({ m, i }) => (
            <Label key={m} x={x(i)} y={height - 6} width={plotW}>
              {i === months.length - 1 ? monthTick(m) : monthShort(m)}
            </Label>
          ))}
        </svg>
      </div>
      {full && (
        <Legend items={[
          { label: 'Saved so far', tone: 'in-essentials' },
          { label: 'Current pace', tone: 'in-band' },
          ...(more ? [{ label: `With ${cash(extra * 100)} more`, tone: 'in-set-aside' }] : []),
        ]} />
      )}
    </figure>
  );
}
