import { useEffect, useState, useRef } from 'react';
import { loadSummaryData, loadCalendarData, loadWatchlistPrices } from '../api.js';

// ── Default watchlist ─────────────────────────────────────────────────────────
const DEFAULTS = [
  { id: 'vix',   label: 'VIX',         ticker: 'VIX Index',     threshold: 25,   direction: 'above' },
  { id: 'hy',    label: 'HY Spread',   ticker: 'LF98OAS Index', threshold: 500,  direction: 'above' },
  { id: 'us10y', label: 'US 10Y',      ticker: 'USGG10Y Index', threshold: 5.0,  direction: 'above' },
  { id: 'us2y',  label: 'US 2Y',       ticker: 'USGG2Y Index',  threshold: 4.0,  direction: 'below' },
];

function loadWatchlist() {
  try {
    const s = localStorage.getItem('macrolens_watchlist');
    return s ? JSON.parse(s) : DEFAULTS;
  } catch { return DEFAULTS; }
}
function saveWatchlist(items) {
  try { localStorage.setItem('macrolens_watchlist', JSON.stringify(items)); } catch {}
}

// ── Procedural morning note ───────────────────────────────────────────────────
function buildNote(summary, calendar) {
  if (!summary) return '';
  const { regime, difficulty_score, yield_curve_shape, yield_curve_bps, top_sector,
          top_sector_return, bottom_sector, bottom_sector_return,
          dominant_factor, dominant_factor_regime } = summary;

  const bpsStr = yield_curve_bps >= 0 ? `+${yield_curve_bps}` : `${yield_curve_bps}`;

  const diffLine = {
    CALM:     `Trading conditions are calm (Difficulty ${Math.round(difficulty_score)}/100) with volatility compressed and spreads tight — an environment conducive to clean execution.`,
    LOW:      `Trading conditions remain orderly (Difficulty ${Math.round(difficulty_score)}/100). Spreads are manageable and price discovery is functioning normally.`,
    MODERATE: `Trading difficulty is elevated at ${Math.round(difficulty_score)}/100 — moderate stress signals warrant tighter position sizing and attentiveness to intraday liquidity.`,
    HIGH:     `Trading difficulty is high (${Math.round(difficulty_score)}/100). Slippage risk is meaningful; widen execution windows and be selective with larger orders.`,
    EXTREME:  `Extreme trading conditions (${Math.round(difficulty_score)}/100). Execution is severely impaired — crisis-like dynamics. Reduce size, avoid illiquid names, and use limit orders.`,
  }[regime] || '';

  const curveLine = {
    INVERTED: `The yield curve is inverted at ${bpsStr}bps — a persistent inversion historically associated with tightening financial conditions and elevated recession risk over a 12–18 month horizon.`,
    FLAT:     `The yield curve is flat at ${bpsStr}bps, suggesting a market at an inflection point — neither pricing in strong growth nor imminent recession. Watch for a directional break.`,
    NORMAL:   `The yield curve is positively sloped at ${bpsStr}bps, a constructive backdrop for financials and consistent with markets pricing in moderate growth.`,
    STEEP:    `The yield curve is steeply sloped at ${bpsStr}bps — strong steepening typically signals either growth optimism or term premium expansion as longer-duration paper is sold off.`,
  }[yield_curve_shape] || '';

  const equityLine = `In equities, the dominant theme is ${dominant_factor_regime} (${dominant_factor}). ${top_sector} is today's leader at +${top_sector_return?.toFixed(1)}%, while ${bottom_sector} is the laggard at ${bottom_sector_return?.toFixed(1)}%.`;

  const upcoming = (calendar?.events || []).filter(e => e.status === 'UPCOMING').slice(0, 2);
  const watchLine = upcoming.length
    ? `Key events to watch: ${upcoming.map(e => `${e.market} ${e.event} (${e.date})`).join(' and ')}.`
    : `No major scheduled releases in the immediate term — focus on price action and flow signals.`;

  return [diffLine, curveLine, equityLine, watchLine].join('\n\n');
}

// ─────────────────────────────────────────────────────────────────────────────
export default function MorningBriefPanel({ market }) {
  const [summary, setSummary]   = useState(null);
  const [calendar, setCalendar] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  // Watchlist state
  const [watchlist, setWatchlist]   = useState(loadWatchlist);
  const [wlPrices, setWlPrices]     = useState({});
  const [adding, setAdding]         = useState(false);
  const [newItem, setNewItem]       = useState({ label: '', ticker: '', threshold: '', direction: 'above' });

  // Load summary + calendar
  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([loadSummaryData(market), loadCalendarData()])
      .then(([s, c]) => { setSummary(s); setCalendar(c); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [market]);

  // Load watchlist prices whenever watchlist changes
  useEffect(() => {
    const tickers = watchlist.map(i => i.ticker).filter(t => !t.startsWith('__'));
    if (!tickers.length) return;
    loadWatchlistPrices(tickers)
      .then(d => setWlPrices(d.prices || {}))
      .catch(() => {});
  }, [watchlist, market]);

  // Persist watchlist
  useEffect(() => { saveWatchlist(watchlist); }, [watchlist]);

  const note = buildNote(summary, calendar);

  const addItem = () => {
    if (!newItem.label || !newItem.ticker || !newItem.threshold) return;
    const item = { ...newItem, id: Date.now().toString(), threshold: parseFloat(newItem.threshold) };
    setWatchlist(prev => [...prev, item]);
    setNewItem({ label: '', ticker: '', threshold: '', direction: 'above' });
    setAdding(false);
  };

  const removeItem = id => setWatchlist(prev => prev.filter(i => i.id !== id));

  const isTriggered = item => {
    const v = wlPrices[item.ticker];
    if (v === undefined) return false;
    return item.direction === 'above' ? v > item.threshold : v < item.threshold;
  };

  const triggeredCount = watchlist.filter(isTriggered).length;

  if (error) return (
    <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>
      Failed to load data: {error}<br />
      <span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span>
    </div>
  );

  return (
    <>
      {/* ── Morning Note ── */}
      <div className="slabel"><em>//</em> MORNING NOTE</div>
      <div className="ai-box" style={{ marginBottom: '1.2rem' }}>
        <div className="ai-hdr">
          <div className="aidot" />
          MARKET BRIEF — {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase()}
        </div>
        {loading ? (
          <div className="ai-txt loading">Generating brief…</div>
        ) : (
          <div className="ai-txt" style={{ whiteSpace: 'pre-wrap' }}>{note}</div>
        )}
      </div>

      {/* ── Key Signal Summary Cards ── */}
      {summary && (
        <>
          <div className="slabel"><em>//</em> KEY SIGNALS</div>
          <div className="g4" style={{ marginBottom: '1.2rem' }}>
            <div className="card">
              <div className="ctitle">DIFFICULTY</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '2.2rem', color:
                summary.regime === 'EXTREME' ? 'var(--red)' : summary.regime === 'HIGH' ? 'var(--orange)' :
                summary.regime === 'MODERATE' ? 'var(--gold)' : summary.regime === 'LOW' ? 'var(--acc)' : 'var(--green)'
              }}>{Math.round(summary.difficulty_score)}</div>
              <div className={`diff-regime regime-${summary.regime?.toLowerCase()}`} style={{ marginTop: '.4rem', fontSize: '.72rem' }}>
                {summary.regime}
              </div>
            </div>
            <div className="card">
              <div className="ctitle">YIELD CURVE</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '2.2rem', color:
                summary.yield_curve_shape === 'INVERTED' ? 'var(--red)' : summary.yield_curve_shape === 'FLAT' ? 'var(--gold)' :
                summary.yield_curve_shape === 'STEEP' ? 'var(--green)' : 'var(--acc)'
              }}>{summary.yield_curve_shape}</div>
              <div style={{ fontSize: '.75rem', color: 'var(--dim)', marginTop: '.4rem' }}>
                2s10s: {summary.yield_curve_bps >= 0 ? '+' : ''}{summary.yield_curve_bps} bps
              </div>
            </div>
            <div className="card">
              <div className="ctitle">LEADING SECTOR</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '1.6rem', color: 'var(--green)', lineHeight: 1.2, marginTop: '.2rem' }}>
                {summary.top_sector}
              </div>
              <div style={{ fontSize: '.8rem', color: 'var(--green)', marginTop: '.4rem' }}>
                +{summary.top_sector_return?.toFixed(1)}%
              </div>
            </div>
            <div className="card">
              <div className="ctitle">LAGGING SECTOR</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '1.6rem', color: 'var(--red)', lineHeight: 1.2, marginTop: '.2rem' }}>
                {summary.bottom_sector}
              </div>
              <div style={{ fontSize: '.8rem', color: 'var(--red)', marginTop: '.4rem' }}>
                {summary.bottom_sector_return?.toFixed(1)}%
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Alert Thresholds ── */}
      <div className="slabel">
        <em>//</em> ALERT THRESHOLDS
        {triggeredCount > 0 && (
          <span style={{ marginLeft: '.6rem', fontSize: '.72rem', color: 'var(--red)', fontFamily: 'var(--fmono)' }}>
            ● {triggeredCount} TRIGGERED
          </span>
        )}
      </div>
      <div className="card" style={{ marginBottom: '1.2rem' }}>
        <table className="wl-table">
          <thead>
            <tr>
              <th>LABEL</th><th>TICKER</th><th>CURRENT</th><th>THRESHOLD</th><th>DIRECTION</th><th>STATUS</th><th></th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map(item => {
              const cur = wlPrices[item.ticker];
              const triggered = isTriggered(item);
              return (
                <tr key={item.id} className={triggered ? 'wl-triggered' : ''}>
                  <td style={{ color: 'var(--text)' }}>{item.label}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.7rem' }}>{item.ticker}</td>
                  <td style={{ color: triggered ? (item.direction === 'above' ? 'var(--red)' : 'var(--green)') : 'var(--text)' }}>
                    {cur !== undefined ? cur.toFixed(2) : '—'}
                  </td>
                  <td style={{ color: 'var(--dim)' }}>
                    {item.direction === 'above' ? '>' : '<'} {item.threshold}
                  </td>
                  <td style={{ color: 'var(--dim)', fontSize: '.7rem', textTransform: 'uppercase' }}>
                    {item.direction}
                  </td>
                  <td>
                    <span className={`wl-pill ${triggered ? 'wl-pill-alert' : 'wl-pill-ok'}`}>
                      {triggered ? '● ALERT' : '○ OK'}
                    </span>
                  </td>
                  <td>
                    <button className="wl-remove" onClick={() => removeItem(item.id)}>✕</button>
                  </td>
                </tr>
              );
            })}
            {adding && (
              <tr className="wl-add-row">
                <td><input className="wl-input" placeholder="Label" value={newItem.label} onChange={e => setNewItem(p => ({...p, label: e.target.value}))} /></td>
                <td><input className="wl-input" placeholder="Bloomberg ticker" value={newItem.ticker} onChange={e => setNewItem(p => ({...p, ticker: e.target.value}))} /></td>
                <td colSpan={2}><input className="wl-input" placeholder="Threshold" type="number" value={newItem.threshold} onChange={e => setNewItem(p => ({...p, threshold: e.target.value}))} /></td>
                <td>
                  <select className="wl-input" value={newItem.direction} onChange={e => setNewItem(p => ({...p, direction: e.target.value}))}>
                    <option value="above">Above</option>
                    <option value="below">Below</option>
                  </select>
                </td>
                <td colSpan={2} style={{ display: 'flex', gap: '.4rem', padding: '.3rem 0' }}>
                  <button className="wl-confirm" onClick={addItem}>Add</button>
                  <button className="wl-cancel" onClick={() => setAdding(false)}>Cancel</button>
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {!adding && (
          <button className="wl-add-btn" onClick={() => setAdding(true)}>+ Add Alert</button>
        )}
      </div>

      {/* ── Upcoming events quick view ── */}
      {calendar && (
        <>
          <div className="slabel"><em>//</em> UPCOMING EVENTS</div>
          <div className="card">
            <table className="cal-table">
              <thead>
                <tr><th>DATE</th><th>MKT</th><th>EVENT</th><th>PERIOD</th><th>PREV</th><th>EXP</th><th>IMPLICATION</th></tr>
              </thead>
              <tbody>
                {calendar.events.filter(e => e.status === 'UPCOMING').map((ev, i) => (
                  <tr key={i}>
                    <td style={{ color: 'var(--acc)', whiteSpace: 'nowrap' }}>{ev.date}</td>
                    <td><span className="mkt-flag">{ev.market}</span></td>
                    <td style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.event}</td>
                    <td style={{ color: 'var(--dim)', fontSize: '.72rem' }}>{ev.period}</td>
                    <td style={{ color: 'var(--dim)' }}>{ev.previous}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : ''}</td>
                    <td style={{ color: 'var(--text)' }}>{ev.expected}{ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : ''}</td>
                    <td style={{ color: 'var(--dim)', fontSize: '.72rem', maxWidth: 320 }}>{ev.implication}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
