import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getCalendar, getCalendarDay, money } from '../api.js';
import { DetailPanel, PButton, StatTile, txAmount } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { CashFlowTabs } from './InsightsParts.jsx';
import { onCalendarUrl, readCalendarUrl, writeCalendarUrl, writeTxUrl } from '../router.js';
import './calendar.css';

/**
 * Cash flow › Calendar (Pearl THL-245 CAL-01 to CAL-05; THL-255), at
 * /cash-flow/calendar, between Transactions and Insights.
 *
 * A month, Sunday first. A past day is a faint lagoon with a ✓ when the
 * month was on or under her usual pace at the end of it, a faint rose with
 * a ▲ when spending had moved ahead, and plain when there's no usual month
 * to compare with. Colour is never the only signal. Today is outlined.
 * Upcoming days list what's due: bills (signed, money out), pay (money in)
 * and, on the 1st, the chests' amounts moving from the Anchor (muted, not
 * spending). No cell carries an amount of its own: safe to spend stays
 * monthly, and no day is ever called anything harsher than "ahead".
 *
 * Tap a day (CAL-02, CAL-03): what was spent, what's due, and one calm line
 * on why it's shaded. On a phone (CAL-05) the grid is compact — a dot means
 * something's due — with a "Coming up" list beneath it.
 */
export default function CalendarPanel({ onTab, version }) {
  const [route, setRoute] = useState(() => readCalendarUrl() ?? { month: '' });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [day, setDay] = useState(null);

  const load = useCallback((month) => {
    setError(null);
    return getCalendar(month).then(setData).catch(setError);
  }, []);
  useEffect(() => { load(route.month); }, [load, route.month, version]);
  useEffect(() => onCalendarUrl(() => {
    const next = readCalendarUrl();
    if (next) setRoute(next);
  }), []);

  const go = (month) => { writeCalendarUrl({ month }); setRoute({ month }); };
  const seeTransactions = (iso) => {
    writeTxUrl({ filters: { month: iso.slice(0, 7), day: iso } }, { push: true });
    onTab?.('transactions');
  };

  if (error) return <div className="pk cal-page"><ErrorNote error={error} onRetry={() => load(route.month)} /></div>;
  if (!data) return <div className="pk cal-page"><p className="pk-muted" role="status">Loading the calendar…</p></div>;

  return (
    <div className="pk cal-page">
      <header className="hm-head">
        <p className="pk-overline accent">{`${monthWords(data.today.slice(0, 7))} ${data.today.slice(0, 4)}`}</p>
        <h1 className="pk-h1">Cash flow</h1>
      </header>
      <CashFlowTabs current="calendar" onTab={onTab} />
      <Totals totals={data.totals} />
      <MonthGrid data={data} onPrev={() => go(data.prev.month)} onNext={() => go(data.next.month)}
                 onDay={setDay} />
      <p className="pk-muted cal-hint">
        Tap a day for what was spent, what’s due, and why it’s shaded. A dot means something’s due.
      </p>
      <ComingUp items={data.coming_up} />
      {day && (
        <DayPanel iso={day} onClose={() => setDay(null)} onTransactions={() => seeTransactions(day)} />
      )}
    </div>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const monthWords = (month) => MONTHS[Number(month.slice(5, 7)) - 1];
export const shortDay = (iso) => `${SHORT[Number(iso.slice(5, 7)) - 1]} ${Number(iso.slice(8, 10))}`;

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** The three figures over the grid (CAL-01). */
export function Totals({ totals }) {
  const far = totals.so_far ? ' so far' : '';
  return (
    <div className="pk-tiles cal-totals">
      <StatTile label={`Spent${far}`} value={money(totals.spent, { cents: true })} />
      <StatTile label={`Income${far}`} value={money(totals.income, { cents: true })} />
      <StatTile label="Moving money" value={money(totals.moving, { cents: true })} />
    </div>
  );
}

/** The ✓ or ▲ a shaded day carries, so colour is never the only signal. */
export function Marker({ state, small = false }) {
  if (state === 'on') return <span className={`cal-mark on${small ? ' sm' : ''}`} aria-hidden="true"><PIcon name="check" size={small ? 9 : 12} /></span>;
  if (state === 'ahead') {
    return (
      <span className={`cal-mark ahead${small ? ' sm' : ''}`} aria-hidden="true">
        <svg viewBox="0 0 10 10" width={small ? 7 : 10} height={small ? 7 : 10}><polygon points="5,1 9.5,9 0.5,9" /></svg>
      </span>
    );
  }
  return null;
}

/** What a cell says to a screen reader. */
export function cellWords(c) {
  const when = c.in_month ? `${c.day}` : shortDay(c.date);
  const state = { on: 'on or under your usual pace', ahead: 'spending moved ahead of your usual pace',
                  none: 'no data yet', today: 'today', future: '', outside: '' }[c.state] ?? '';
  const due = (c.due ?? []).map((d) => `${d.label} ${dueAmount(d)}`).join(', ');
  return [when, state, due].filter(Boolean).join(', ');
}

export function dueAmount(d) {
  if (d.kind === 'pay') return txAmount(d.amount, { inflow: true });
  if (d.kind === 'chest') return money(d.amount);
  return txAmount(d.amount, { signed: true });
}

/** The month grid, Sunday first, six rows (CAL-01). */
export function MonthGrid({ data, onPrev, onNext, onDay }) {
  // A sixth row that is all next month is dropped on a phone.
  const spare = data.cells.slice(35).every((c) => !c.in_month);
  return (
    <section className="hm-card cal-card" aria-labelledby="cal-title">
      <div className="hm-row-between cal-head">
        <h2 className="pk-h2" id="cal-title">{data.label}</h2>
        <div className="cal-nav">
          <button type="button" className="hm-link" onClick={onPrev} aria-label={`Back to ${data.prev.label}`}>
            <PIcon name="chevronRight" size={14} className="in-flip" /><span className="cal-nav-word"> {data.prev.label}</span>
          </button>
          <button type="button" className="hm-link" onClick={onNext} aria-label={`On to ${data.next.label}`}>
            <span className="cal-nav-word">{data.next.label} </span><PIcon name="chevronRight" size={14} />
          </button>
        </div>
      </div>
      <div className="cal-weekdays" aria-hidden="true">
        {WEEKDAYS.map((d) => <span key={d} className="pk-overline">{d}</span>)}
      </div>
      <div className="cal-grid" role="grid" aria-label={data.label}>
        {data.cells.map((c, k) => (
          <button key={c.date} type="button" role="gridcell"
                  className={`cal-cell ${c.state}${c.in_month ? '' : ' outside'}${c.due.length ? ' has-due' : ''}${k >= 35 && spare ? ' spare' : ''}`}
                  aria-label={cellWords(c)} onClick={() => onDay?.(c.date)}>
            <span className="cal-top">
              <span className="cal-num">{c.day}</span>
              <Marker state={c.state} />
            </span>
            {c.due.length > 0 && (
              <span className="cal-due" aria-hidden="true">
                {c.due.slice(0, 2).map((d) => (
                  <span key={`${d.kind}-${d.label}`} className={`cal-due-item ${d.kind}`}>
                    <span className="cal-due-label">{d.label}</span>
                    <span className="cal-due-amt">{dueAmount(d)}</span>
                  </span>
                ))}
                {c.due.length > 2 && <span className="cal-due-more">{`+${c.due.length - 2} more`}</span>}
              </span>
            )}
            {c.due.length > 0 && <span className="cal-dot" aria-hidden="true" />}
          </button>
        ))}
      </div>
      <ul className="cal-legend" aria-label="What the shading means">
        {data.legend.map((l) => (
          <li key={l.key}>
            <span className={`cal-swatch ${l.key}`} aria-hidden="true"><Marker state={l.key} small /></span>
            {l.label}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** CAL-05: the list under the compact grid. */
export function ComingUp({ items }) {
  return (
    <section className="hm-card cal-coming" aria-labelledby="cal-coming-title">
      <h2 className="pk-h2" id="cal-coming-title">Coming up</h2>
      {items.length === 0 ? (
        <p className="pk-muted">Nothing due before the month ends.</p>
      ) : (
        <ul className="cal-list">
          {items.map((d) => (
            <li key={`${d.date}-${d.kind}-${d.label}`}>
              <span className="pk-muted cal-when">{shortDay(d.date)}</span>
              <span className="cal-what">{d.label}</span>
              <span className={`cal-amt ${d.kind}`}>{dueAmount(d)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** CAL-02 (a past day) and CAL-03 (an upcoming one). */
export function DayPanel({ iso, onClose, onTransactions }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let live = true;
    setD(null);
    getCalendarDay(iso).then((x) => { if (live) setD(x); }).catch((e) => { if (live) setError(e); });
    return () => { live = false; };
  }, [iso]);
  if (error) {
    return <DetailPanel label="Day" overline="Day" onClose={onClose} className="on-card"><ErrorNote error={error} /></DetailPanel>;
  }
  if (!d) {
    return <DetailPanel label="Day" overline="Day" onClose={onClose} className="on-card"><p className="pk-muted" role="status">Loading…</p></DetailPanel>;
  }
  return <DayBody d={d} onClose={onClose} onTransactions={onTransactions} />;
}

export function DayBody({ d, onClose, onTransactions }) {
  const shaded = d.state === 'on' || d.state === 'ahead';
  return (
    <DetailPanel label={d.label} overline="Day" onClose={onClose} className="on-card cal-day">
      <h1 className="pk-h1">{d.label}</h1>
      <div className={`cal-reason ${d.state}`} role="note">
        {shaded && <Marker state={d.state} />}
        <p>{d.reason}</p>
      </div>
      {!d.today && d.past && (
        <>
          <p className="pk-overline">Spent</p>
          {d.spent.length === 0 ? <p className="pk-muted">Nothing was spent.</p> : (
            <ul className="cal-rows">
              {d.spent.map((r) => (
                <li key={r.id}>
                  <span className="cal-row-text">
                    <span>{r.merchant}</span>
                    <span className="pk-label pk-muted">{r.category}{r.unusual ? ' · unusual' : ''}</span>
                  </span>
                  <span className="cal-amt bill">{txAmount(r.amount, { signed: true })}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {d.today && (
        <>
          <p className="pk-overline">Spent so far</p>
          {d.spent.length === 0 ? <p className="pk-muted">Nothing yet.</p> : (
            <ul className="cal-rows">
              {d.spent.map((r) => (
                <li key={r.id}>
                  <span className="cal-row-text">
                    <span>{r.merchant}</span>
                    <span className="pk-label pk-muted">{r.category}{r.unusual ? ' · unusual' : ''}</span>
                  </span>
                  <span className="cal-amt bill">{txAmount(r.amount, { signed: true })}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <p className="pk-overline">Due</p>
      {d.due.length === 0 ? <p className="pk-muted">{d.past ? 'Nothing was due.' : 'Nothing is due.'}</p> : (
        <ul className="cal-rows">
          {d.due.map((x) => (
            <li key={`${x.kind}-${x.label}`}>
              <span className="cal-row-text">
                <span>{x.label}</span>
                {x.note && <span className="pk-label pk-muted">{x.note}</span>}
              </span>
              <span className={`cal-amt ${x.kind}`}>{dueAmount(x)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="gl-panel-foot">
        {(d.past || d.today) && d.spent.length > 0
          ? <PButton onClick={onTransactions}>See these transactions</PButton>
          : <PButton onClick={onClose}>Done</PButton>}
      </div>
    </DetailPanel>
  );
}

/** CAL-06: the month strip on Home, one tiny cell per day; it opens the calendar. */
export function CalendarStrip({ strip, onOpen }) {
  if (!strip) return null;
  return (
    <section className="hm-card cal-strip" aria-labelledby="cal-strip-title">
      <div className="hm-row-between">
        <h2 className="pk-h3" id="cal-strip-title">{strip.label}</h2>
        <button type="button" className="hm-link" onClick={onOpen}>
          Open calendar <PIcon name="chevronRight" size={14} />
        </button>
      </div>
      <button type="button" className="cal-strip-days" onClick={onOpen}
              aria-label={`${strip.label}, day by day. Open the calendar`}>
        {strip.cells.map((c) => (
          <span key={c.date} className={`cal-mini ${c.state}${c.due ? ' has-due' : ''}`}>
            {c.state === 'ahead' && <Marker state="ahead" small />}
            {c.due && c.state !== 'ahead' && <span className="cal-dot" />}
          </span>
        ))}
      </button>
      <p className="pk-muted">{strip.line}</p>
    </section>
  );
}
