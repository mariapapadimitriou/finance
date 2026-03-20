import { useEffect, useState } from 'react';
import { loadInflationData, loadCentralBanksData, loadCalendarData } from '../api.js';

const ALL_MARKETS = ['US', 'CA', 'MX', 'BR', 'CL'];

const BIAS_CLASS = { HOLD: 'bias-hold', EASING: 'bias-easing', TIGHTENING: 'bias-tightening' };

const TREND_ICON  = { UP: '↑', DOWN: '↓', FLAT: '→' };
const TREND_COLOR = { UP: 'var(--red)', DOWN: 'var(--green)', FLAT: 'var(--gold)' };

const BEAT_MISS_CLASS = { BEAT: 'bm-beat', MISS: 'bm-miss', INLINE: 'bm-inline' };
const BEAT_MISS_LABEL = { BEAT: 'BEAT', MISS: 'MISS', INLINE: 'IN LINE' };

export default function MacroPanel({ market }) {
  const [inflation, setInflation]   = useState(null);
  const [cb, setCb]                 = useState(null);
  const [calendar, setCalendar]     = useState(null);
  const [allCbs, setAllCbs]         = useState(null);
  const [allInfl, setAllInfl]       = useState(null);
  const [error, setError]           = useState(null);

  useEffect(() => {
    setInflation(null); setCb(null); setCalendar(null); setAllCbs(null); setAllInfl(null);
    setError(null);

    Promise.all([
      loadInflationData(market),
      loadCentralBanksData(market),
      loadCalendarData(),
      Promise.all(ALL_MARKETS.map(m => loadCentralBanksData(m))),
      Promise.all(ALL_MARKETS.map(m => loadInflationData(m))),
    ]).then(([infl, cbData, cal, cbs, infls]) => {
      setInflation(infl);
      setCb(cbData);
      setCalendar(cal);
      setAllCbs(cbs);
      setAllInfl(infls);
    }).catch(err => setError(err.message));
  }, [market]);

  if (error) return (
    <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>
      Failed to load data: {error}<br />
      <span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span>
    </div>
  );

  const loading = !inflation || !cb || !calendar || !allCbs || !allInfl;

  // ── Calendar helpers ─────────────────────────────────────────────────────
  const pastEvents     = calendar?.events.filter(e => e.status === 'PAST').reverse()    || [];
  const upcomingEvents = calendar?.events.filter(e => e.status === 'UPCOMING')          || [];

  return (
    <>
      {/* ── Inflation Dashboard ── */}
      <div className="slabel"><em>//</em> INFLATION DASHBOARD — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>
      ) : (
        <div className="g4" style={{ marginBottom: '1.2rem' }}>
          {inflation.readings.map((r, i) => (
            <div className="card" key={i}>
              <div className="ctitle">{r.label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '.5rem' }}>
                <span style={{ fontFamily: 'var(--fhead)', fontSize: '2.4rem', lineHeight: 1,
                  color: r.current > 3.5 ? 'var(--red)' : r.current > 2.5 ? 'var(--gold)' : 'var(--green)' }}>
                  {r.current}
                </span>
                <span style={{ fontSize: '1rem', color: 'var(--dim)' }}>{r.unit}</span>
                <span style={{ fontSize: '1.3rem', color: TREND_COLOR[r.trend], marginLeft: '.2rem' }}>
                  {TREND_ICON[r.trend]}
                </span>
              </div>
              <div style={{ fontSize: '.75rem', color: 'var(--dim)', marginTop: '.35rem' }}>
                Prev: <span style={{ color: 'var(--text)' }}>{r.prev}{r.unit}</span>
                <span style={{ marginLeft: '.6rem' }}>{r.period}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── All Markets Inflation Snapshot ── */}
      <div className="slabel"><em>//</em> INFLATION SNAPSHOT — ALL MARKETS</div>
      {!allInfl ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>
      ) : (
        <div className="card" style={{ marginBottom: '1.2rem', overflowX: 'auto' }}>
          <table className="tenor-tbl">
            <thead>
              <tr>
                <th>MARKET</th>
                {allInfl[0]?.readings.map((r, i) => <th key={i}>{r.label.toUpperCase()}</th>)}
              </tr>
            </thead>
            <tbody>
              {ALL_MARKETS.map((mkt, mi) => {
                const readings = allInfl[mi]?.readings || [];
                return (
                  <tr key={mkt}>
                    <td style={{ color: 'var(--acc)', fontWeight: 600 }}>{mkt}</td>
                    {readings.map((r, i) => (
                      <td key={i} style={{ color: r.current > 3.5 ? 'var(--red)' : r.current > 2.5 ? 'var(--gold)' : 'var(--green)' }}>
                        {r.current}{r.unit} <span style={{ color: TREND_COLOR[r.trend], fontSize: '.7rem' }}>{TREND_ICON[r.trend]}</span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Central Bank Rates ── */}
      <div className="slabel"><em>//</em> CENTRAL BANK RATES</div>
      {!allCbs ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>
      ) : (
        <div className="g3" style={{ marginBottom: '1.2rem' }}>
          {allCbs.map((cbItem, i) => (
            <div className="card" key={i}>
              <div className="ctitle">{cbItem.bank}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem', marginBottom: '.5rem' }}>
                <span style={{ fontFamily: 'var(--fhead)', fontSize: '2.4rem', lineHeight: 1, color: 'var(--text)' }}>
                  {cbItem.policy_rate}
                </span>
                <span style={{ fontSize: '.85rem', color: 'var(--dim)' }}>%</span>
                <span style={{ fontSize: '.85rem', marginLeft: '.4rem',
                  color: cbItem.last_change > 0 ? 'var(--red)' : cbItem.last_change < 0 ? 'var(--green)' : 'var(--dim)' }}>
                  ({cbItem.last_change > 0 ? '+' : ''}{cbItem.last_change * 100 | 0}bps)
                </span>
              </div>
              <div style={{ marginBottom: '.5rem' }}>
                <span className={`cb-bias ${BIAS_CLASS[cbItem.bias] || 'bias-hold'}`}>{cbItem.bias}</span>
              </div>
              <div style={{ fontSize: '.72rem', color: 'var(--dim)', marginBottom: '.3rem' }}>
                Last change: <span style={{ color: 'var(--text)' }}>{cbItem.last_change_date}</span>
              </div>
              <div style={{ fontSize: '.72rem', color: 'var(--dim)', marginBottom: '.5rem' }}>
                Next meeting: <span style={{ color: 'var(--acc)' }}>{cbItem.next_meeting}</span>
              </div>
              <div style={{ fontSize: '.72rem', color: 'var(--dim)', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: '.5rem' }}>
                {cbItem.bias_note}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Economic Calendar — Recent ── */}
      <div className="slabel"><em>//</em> RECENT RELEASES</div>
      {!calendar ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>
      ) : (
        <div className="card" style={{ marginBottom: '1.2rem', overflowX: 'auto' }}>
          <table className="cal-table">
            <thead>
              <tr><th>DATE</th><th>MKT</th><th>EVENT</th><th>PERIOD</th><th>PREV</th><th>EXP</th><th>ACTUAL</th><th>RESULT</th><th>IMPLICATION</th></tr>
            </thead>
            <tbody>
              {pastEvents.map((ev, i) => (
                <tr key={i} className="cal-past">
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--dim)' }}>{ev.date}</td>
                  <td><span className="mkt-flag">{ev.market}</span></td>
                  <td style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.event}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem' }}>{ev.period}</td>
                  <td style={{ color: 'var(--dim)' }}>{ev.previous}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : (ev.unit === 'K' ? 'K' : '')}</td>
                  <td style={{ color: 'var(--dim)' }}>{ev.expected}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : (ev.unit === 'K' ? 'K' : '')}</td>
                  <td style={{ color: 'var(--text)', fontWeight: 600 }}>{ev.actual}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : (ev.unit === 'K' ? 'K' : '')}</td>
                  <td>
                    {ev.beat_miss && (
                      <span className={`bm-tag ${BEAT_MISS_CLASS[ev.beat_miss] || ''}`}>
                        {BEAT_MISS_LABEL[ev.beat_miss]}
                      </span>
                    )}
                  </td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem', maxWidth: 300 }}>{ev.implication}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Economic Calendar — Upcoming ── */}
      <div className="slabel"><em>//</em> UPCOMING RELEASES</div>
      {!calendar ? null : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="cal-table">
            <thead>
              <tr><th>DATE</th><th>MKT</th><th>EVENT</th><th>PERIOD</th><th>PREV</th><th>EXPECTED</th><th>IMPLICATION</th></tr>
            </thead>
            <tbody>
              {upcomingEvents.map((ev, i) => (
                <tr key={i} className="cal-upcoming">
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--acc)' }}>{ev.date}</td>
                  <td><span className="mkt-flag">{ev.market}</span></td>
                  <td style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.event}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem' }}>{ev.period}</td>
                  <td style={{ color: 'var(--dim)' }}>{ev.previous}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : (ev.unit === 'K' ? 'K' : '')}</td>
                  <td style={{ color: 'var(--gold)' }}>{ev.expected}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : (ev.unit === 'K' ? 'K' : '')}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem', maxWidth: 340 }}>{ev.implication}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
