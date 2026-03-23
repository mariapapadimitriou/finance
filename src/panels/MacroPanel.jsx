import { useEffect, useState } from 'react';
import {
  loadInflationData, loadCentralBanksData, loadCalendarData, loadSummaryData,
  loadIndicatorHistory, loadGrowthData, loadFXData, cssVar,
} from '../api.js';
import ChartCanvas from '../components/ChartCanvas.jsx';

// ── Procedural morning note ───────────────────────────────────────────────────
function buildNote(summary, calendar) {
  if (!summary) return '';
  const { regime, difficulty_score, yield_curve_shape, yield_curve_bps,
          top_sector, top_sector_return, bottom_sector, bottom_sector_return,
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

  const equityLine = `In equities, the dominant theme is ${dominant_factor_regime} (${dominant_factor}). ${top_sector} is leading at +${top_sector_return?.toFixed(1)}%, while ${bottom_sector} is lagging at ${bottom_sector_return?.toFixed(1)}%.`;

  const upcoming = (calendar?.events || []).filter(e => e.status === 'UPCOMING').slice(0, 2);
  const watchLine = upcoming.length
    ? `Key events to watch: ${upcoming.map(e => `${e.event} (${e.date})`).join(' and ')}.`
    : `No major scheduled releases in the immediate term — focus on price action and flow signals.`;

  return [diffLine, curveLine, equityLine, watchLine].join('\n\n');
}

// ── Constants ─────────────────────────────────────────────────────────────────
const BIAS_CLASS  = { HOLD: 'bias-hold', EASING: 'bias-easing', TIGHTENING: 'bias-tightening' };
const TREND_ICON  = { UP: '↑', DOWN: '↓', FLAT: '→' };
const TREND_COLOR = { UP: 'var(--red)', DOWN: 'var(--green)', FLAT: 'var(--gold)' };
const BM_CLASS    = { BEAT: 'bm-beat', MISS: 'bm-miss', INLINE: 'bm-inline' };
const BM_LABEL    = { BEAT: 'BEAT', MISS: 'MISS', INLINE: 'IN LINE' };

function inflColor(val) {
  return val > 3.5 ? 'var(--red)' : val > 2.5 ? 'var(--gold)' : 'var(--green)';
}
function growthColor(label, val) {
  if (label.includes('PMI'))        return val > 52 ? 'var(--green)' : val < 50 ? 'var(--red)' : 'var(--gold)';
  if (label.includes('Unemploy'))   return val < 4.5 ? 'var(--green)' : val < 6 ? 'var(--gold)' : 'var(--red)';
  return val > 2 ? 'var(--green)' : val > 0 ? 'var(--gold)' : 'var(--red)';
}

// ─────────────────────────────────────────────────────────────────────────────
export default function MacroPanel({ market, theme }) {
  const [summary, setSummary]     = useState(null);
  const [inflation, setInflation] = useState(null);
  const [cb, setCb]               = useState(null);
  const [calendar, setCalendar]   = useState(null);
  const [growth, setGrowth]       = useState(null);
  const [fx, setFx]               = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const [selInfl, setSelInfl]               = useState(null); // { ticker, label, unit }
  const [inflHistory, setInflHistory]       = useState(null);
  const [inflHistLoading, setInflHistLoading] = useState(false);

  const [selGrowth, setSelGrowth]                 = useState(null);
  const [growthHistory, setGrowthHistory]         = useState(null);
  const [growthHistLoading, setGrowthHistLoading] = useState(false);

  const [cbHistory, setCbHistory]       = useState(null);
  const [cbHistLoading, setCbHistLoading] = useState(false);

  // ── Load all data ──────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setSummary(null); setInflation(null); setCb(null); setCalendar(null);
    setGrowth(null); setFx(null); setError(null);
    setSelInfl(null); setSelGrowth(null);
    setCbHistory(null);

    Promise.all([
      loadSummaryData(market),
      loadInflationData(market),
      loadCentralBanksData(market),
      loadCalendarData(market),
      loadGrowthData(market),
      loadFXData(market),
    ]).then(([sum, infl, cbData, cal, growthData, fxData]) => {
      setSummary(sum);
      setInflation(infl);
      setCb(cbData);
      setCalendar(cal);
      setGrowth(growthData);
      setFx(fxData);
      setLoading(false);
    }).catch(err => { setError(err.message); setLoading(false); });
  }, [market]);

  // ── Auto-load CB rate history ──────────────────────────────────────────────
  useEffect(() => {
    if (!cb?.rate_ticker) return;
    setCbHistLoading(true);
    loadIndicatorHistory(cb.rate_ticker, 36)
      .then(d => { setCbHistory(d); setCbHistLoading(false); })
      .catch(() => setCbHistLoading(false));
  }, [cb?.rate_ticker]);

  // ── Load indicator history — inflation ────────────────────────────────────
  useEffect(() => {
    if (!selInfl) { setInflHistory(null); return; }
    setInflHistLoading(true);
    loadIndicatorHistory(selInfl.ticker, 36)
      .then(d => { setInflHistory(d); setInflHistLoading(false); })
      .catch(() => setInflHistLoading(false));
  }, [selInfl]);

  // ── Load indicator history — growth ───────────────────────────────────────
  useEffect(() => {
    if (!selGrowth) { setGrowthHistory(null); return; }
    setGrowthHistLoading(true);
    loadIndicatorHistory(selGrowth.ticker, 36)
      .then(d => { setGrowthHistory(d); setGrowthHistLoading(false); })
      .catch(() => setGrowthHistLoading(false));
  }, [selGrowth]);

  const handleSelect = (ticker, label, unit, section) => {
    if (section === 'inflation') {
      setSelInfl(prev => prev?.ticker === ticker ? null : { ticker, label, unit });
    } else {
      setSelGrowth(prev => prev?.ticker === ticker ? null : { ticker, label, unit });
    }
  };

  // ── Chart builder ──────────────────────────────────────────────────────────
  const buildHistoryChart = (history, indicator) => (_ctx) => {
    const acc  = cssVar('--acc');
    const dim  = cssVar('--chart-dim');
    const grid = cssVar('--chart-grid');
    const bg   = cssVar('--chart-bg');
    const text = cssVar('--chart-text');
    return {
      type: 'line',
      data: {
        labels: history.dates,
        datasets: [{
          data: history.values,
          borderColor: acc,
          backgroundColor: bg,
          fill: false,
          tension: 0.3,
          pointRadius: 2,
          pointHoverRadius: 4,
          borderWidth: 1.5,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: bg, borderColor: dim, borderWidth: 1,
            titleColor: dim, bodyColor: text,
            titleFont: { family: 'IBM Plex Mono', size: 12 },
            bodyFont:  { family: 'IBM Plex Mono', size: 13 },
            callbacks: { label: ctx => ` ${ctx.parsed.y.toFixed(2)}${indicator.unit}` },
          },
        },
        scales: {
          x: { ticks: { color: dim, font: { family: 'IBM Plex Mono', size: 11 }, maxTicksLimit: 9 }, grid: { color: grid } },
          y: {
            ticks: { color: dim, font: { family: 'IBM Plex Mono', size: 11 },
                     callback: v => `${parseFloat(v).toFixed(1)}${indicator.unit}` },
            grid: { color: grid },
          },
        },
      },
    };
  };

  // ── CB helpers ─────────────────────────────────────────────────────────────
  const decisionSurprise = (change, expected) => {
    const diff = (change - expected) * 100; // in bps
    if (diff > 0.1)  return { label: 'HAWKISH', cls: 'cb-surprise-hawk' };
    if (diff < -0.1) return { label: 'DOVISH',  cls: 'cb-surprise-dove' };
    return { label: 'IN LINE', cls: 'cb-surprise-inline' };
  };

  const buildCBChart = (history) => (_ctx) => {
    const acc  = cssVar('--acc');
    const dim  = cssVar('--chart-dim');
    const grid = cssVar('--chart-grid');
    const bg   = cssVar('--chart-bg');
    const text = cssVar('--chart-text');
    return {
      type: 'line',
      data: {
        labels: history.dates,
        datasets: [{
          data: history.values,
          borderColor: acc,
          backgroundColor: bg,
          fill: false,
          stepped: 'before',
          pointRadius: 2,
          pointHoverRadius: 4,
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: bg, borderColor: dim, borderWidth: 1,
            titleColor: dim, bodyColor: text,
            titleFont: { family: 'IBM Plex Mono', size: 12 },
            bodyFont:  { family: 'IBM Plex Mono', size: 13 },
            callbacks: { label: ctx => ` ${ctx.parsed.y.toFixed(2)}%` },
          },
        },
        scales: {
          x: { ticks: { color: dim, font: { family: 'IBM Plex Mono', size: 11 }, maxTicksLimit: 8 }, grid: { color: grid } },
          y: {
            ticks: { color: dim, font: { family: 'IBM Plex Mono', size: 11 }, callback: v => `${v}%` },
            grid: { color: grid },
          },
        },
      },
    };
  };

  // ── Chart card (per section, independent state) ────────────────────────────
  const ChartPane = ({ section }) => {
    const sel     = section === 'inflation' ? selInfl         : selGrowth;
    const history = section === 'inflation' ? inflHistory     : growthHistory;
    const loading = section === 'inflation' ? inflHistLoading : growthHistLoading;
    const clear   = section === 'inflation' ? () => setSelInfl(null) : () => setSelGrowth(null);

    if (!sel) {
      return (
        <div className="card" style={{ minHeight: 180 }}>
          <div className="chart-placeholder">SELECT AN INDICATOR<br />TO VIEW 36M HISTORY</div>
        </div>
      );
    }
    return (
      <div className="card">
        <div className="ctitle" style={{ marginBottom: '.6rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '.88rem' }}>{sel.label.toUpperCase()} — 36M</span>
          <button
            onClick={clear}
            style={{ background: 'none', border: '1px solid var(--border2)', color: 'var(--dim)',
                     cursor: 'pointer', fontSize: '.65rem', padding: '.12rem .45rem', borderRadius: 2,
                     fontFamily: 'var(--fmono)', letterSpacing: '.05em' }}
          >✕</button>
        </div>
        <div style={{ height: 190, position: 'relative' }}>
          {loading
            ? <div style={{ color: 'var(--dim)', fontSize: '.78rem', padding: '.5rem' }}>Loading…</div>
            : history?.dates?.length > 0
              ? <ChartCanvas buildConfig={buildHistoryChart(history, sel)}
                             deps={[history, sel, theme]} height="100%" />
              : <div style={{ color: 'var(--dim)', fontSize: '.78rem', padding: '.5rem' }}>No data available</div>
          }
        </div>
      </div>
    );
  };

  // ── Helpers ────────────────────────────────────────────────────────────────
  const note       = buildNote(summary, calendar);
  const pastEvents = calendar?.events.filter(e => e.status === 'PAST').reverse()  || [];
  const upcoming   = calendar?.events.filter(e => e.status === 'UPCOMING')        || [];
  const dateLabel  = new Date().toLocaleDateString('en-US',
    { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();

  const unitStr = (ev, val) => val == null ? '—' :
    `${val}${ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : ev.unit === 'K' ? 'K' : ''}`;

  const cardStyle = (ticker, section) => ({
    cursor: 'pointer',
    borderColor: (section === 'inflation' ? selInfl : selGrowth)?.ticker === ticker ? 'var(--acc)' : undefined,
    transition: 'border-color .15s',
  });

  if (error) return (
    <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>
      Failed to load data: {error}<br />
      <span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span>
    </div>
  );

  return (
    <>
      {/* ── Morning Note ── */}
      <div className="slabel"><em>//</em> MORNING NOTE — {market}</div>
      <div className="ai-box" style={{ marginBottom: '1.2rem' }}>
        <div className="ai-hdr">
          <div className="aidot" />
          MARKET BRIEF — {dateLabel}
        </div>
        {loading
          ? <div className="ai-txt loading">Generating brief…</div>
          : <div className="ai-txt" style={{ whiteSpace: 'pre-wrap' }}>{note}</div>
        }
      </div>

      {/* ── Key Signal Cards ── */}
      {summary && (
        <>
          <div className="slabel"><em>//</em> KEY SIGNALS</div>
          <div className="g4" style={{ marginBottom: '1.2rem' }}>
            <div className="card">
              <div className="ctitle">DIFFICULTY</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '2.2rem', color:
                summary.regime === 'EXTREME' ? 'var(--red)' : summary.regime === 'HIGH' ? 'var(--orange)' :
                summary.regime === 'MODERATE' ? 'var(--gold)' : summary.regime === 'LOW' ? 'var(--acc)' : 'var(--green)' }}>
                {Math.round(summary.difficulty_score)}
              </div>
              <div className={`diff-regime regime-${summary.regime?.toLowerCase()}`} style={{ marginTop: '.4rem', fontSize: '.72rem' }}>
                {summary.regime}
              </div>
            </div>
            <div className="card">
              <div className="ctitle">YIELD CURVE</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '2.2rem', color:
                summary.yield_curve_shape === 'INVERTED' ? 'var(--red)' : summary.yield_curve_shape === 'FLAT' ? 'var(--gold)' :
                summary.yield_curve_shape === 'STEEP' ? 'var(--green)' : 'var(--acc)' }}>
                {summary.yield_curve_shape}
              </div>
              <div style={{ fontSize: '.75rem', color: 'var(--dim)', marginTop: '.4rem' }}>
                2s10s: {summary.yield_curve_bps >= 0 ? '+' : ''}{summary.yield_curve_bps} bps
              </div>
            </div>
            <div className="card">
              <div className="ctitle">LEADING SECTOR</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '1.6rem', color: 'var(--green)', lineHeight: 1.2, marginTop: '.2rem' }}>
                {summary.top_sector}
              </div>
              <div style={{ fontSize: '.8rem', color: 'var(--green)', marginTop: '.4rem' }}>+{summary.top_sector_return?.toFixed(1)}%</div>
            </div>
            <div className="card">
              <div className="ctitle">LAGGING SECTOR</div>
              <div style={{ fontFamily: 'var(--fhead)', fontSize: '1.6rem', color: 'var(--red)', lineHeight: 1.2, marginTop: '.2rem' }}>
                {summary.bottom_sector}
              </div>
              <div style={{ fontSize: '.8rem', color: 'var(--red)', marginTop: '.4rem' }}>{summary.bottom_sector_return?.toFixed(1)}%</div>
            </div>
          </div>
        </>
      )}

      {/* ── Inflation ── */}
      <div className="slabel"><em>//</em> INFLATION — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : (
        <div className="g-macro-split">
          <div className="macro-cards-2">
            {inflation?.readings.map((r, i) => (
              <div className="card" key={i}
                onClick={() => r.ticker && handleSelect(r.ticker, r.label, r.unit, 'inflation')}
                style={cardStyle(r.ticker, 'inflation')}
              >
                <div className="ctitle">{r.label}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '.5rem' }}>
                  <span style={{ fontFamily: 'var(--fhead)', fontSize: '2.2rem', lineHeight: 1,
                    color: inflColor(r.current) }}>{r.current}</span>
                  <span style={{ fontSize: '.9rem', color: 'var(--dim)' }}>{r.unit}</span>
                  <span style={{ fontSize: '1.2rem', color: TREND_COLOR[r.trend], marginLeft: '.2rem' }}>
                    {TREND_ICON[r.trend]}
                  </span>
                </div>
                <div style={{ fontSize: '.72rem', color: 'var(--dim)', marginTop: '.3rem' }}>
                  Prev: <span style={{ color: 'var(--text)' }}>{r.prev}{r.unit}</span>
                  <span style={{ marginLeft: '.5rem' }}>{r.period}</span>
                </div>
              </div>
            ))}
          </div>
          <ChartPane section="inflation" />
        </div>
      )}

      {/* ── Growth & Activity ── */}
      <div className="slabel"><em>//</em> GROWTH & ACTIVITY — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : (
        <div className="g-macro-split">
          <div className="macro-cards-3">
            {growth?.readings.map((r, i) => (
              <div className="card" key={i}
                onClick={() => r.ticker && handleSelect(r.ticker, r.label, r.unit, 'growth')}
                style={cardStyle(r.ticker, 'growth')}
              >
                <div className="ctitle">{r.label}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem' }}>
                  <span style={{ fontFamily: 'var(--fhead)', fontSize: '2rem', lineHeight: 1,
                    color: growthColor(r.label, r.current) }}>{r.current}</span>
                  <span style={{ fontSize: '.85rem', color: 'var(--dim)' }}>{r.unit}</span>
                  <span style={{ fontSize: '1.1rem', color: TREND_COLOR[r.trend], marginLeft: '.15rem' }}>
                    {TREND_ICON[r.trend]}
                  </span>
                </div>
                <div style={{ fontSize: '.72rem', color: 'var(--dim)', marginTop: '.3rem' }}>
                  Prev: <span style={{ color: 'var(--text)' }}>{r.prev}{r.unit}</span>
                  <span style={{ marginLeft: '.5rem' }}>{r.period}</span>
                </div>
              </div>
            ))}
          </div>
          <ChartPane section="growth" />
        </div>
      )}

      {/* ── FX Rate (non-USD markets only) ── */}
      {!loading && fx?.fx && (
        <>
          <div className="slabel"><em>//</em> FX RATE — {market}</div>
          <div className="fx-bar">
            <div>
              <div className="fx-pair">{fx.fx.pair}</div>
              <div className="fx-rate">{fx.fx.rate.toFixed(market === 'CL' ? 1 : 4)}</div>
              <div style={{ fontSize: '.73rem', color: 'var(--dim)', marginTop: '.3rem' }}>
                Prev: <span style={{ color: 'var(--text)' }}>{fx.fx.prev.toFixed(market === 'CL' ? 1 : 4)}</span>
                <span style={{ marginLeft: '.7rem', color: TREND_COLOR[fx.fx.trend] }}>
                  {TREND_ICON[fx.fx.trend]} USD {fx.fx.trend === 'UP' ? 'strengthening' : fx.fx.trend === 'DOWN' ? 'weakening' : 'flat'}
                </span>
              </div>
            </div>
            <div className="fx-note">{fx.fx.note}</div>
          </div>
        </>
      )}

      {/* ── Central Bank ── */}
      <div className="slabel"><em>//</em> CENTRAL BANK — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : cb && (
        <div className="g-cb">
          {/* Left: CB info card + decision history table */}
          <div className="card">
            <div className="ctitle" style={{ marginBottom: '.6rem' }}>{cb.bank}</div>

            {/* Rate + bias row */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem', marginBottom: '.5rem' }}>
              <span style={{ fontFamily: 'var(--fhead)', fontSize: '2.8rem', lineHeight: 1, color: 'var(--text)' }}>
                {cb.policy_rate}
              </span>
              <span style={{ fontSize: '.85rem', color: 'var(--dim)' }}>%</span>
              <span style={{ fontSize: '.85rem', marginLeft: '.4rem',
                color: cb.last_change > 0 ? 'var(--red)' : cb.last_change < 0 ? 'var(--green)' : 'var(--dim)' }}>
                ({cb.last_change > 0 ? '+' : ''}{(cb.last_change * 100) | 0}bps)
              </span>
              <span className={`cb-bias ${BIAS_CLASS[cb.bias] || 'bias-hold'}`} style={{ marginLeft: '.6rem' }}>{cb.bias}</span>
            </div>

            {/* Dates */}
            <div style={{ fontSize: '.78rem', color: 'var(--dim)', marginBottom: '.6rem' }}>
              Last change: <span style={{ color: 'var(--text)' }}>{cb.last_change_date}</span>
              <span style={{ margin: '0 .8rem', color: 'var(--border2)' }}>|</span>
              Next meeting: <span style={{ color: 'var(--acc)' }}>{cb.next_meeting}</span>
            </div>

            {/* Bias note */}
            <div style={{ fontSize: '.8rem', color: 'var(--dim)', lineHeight: 1.75,
              borderLeft: '2px solid var(--border2)', paddingLeft: '.9rem', marginBottom: '.9rem' }}>
              {cb.bias_note}
            </div>

            {/* Decision history table */}
            {cb.rate_history?.length > 0 && (
              <>
                <div style={{ fontSize: '.72rem', color: 'var(--dim)', letterSpacing: '.06em', marginBottom: '.3rem' }}>
                  DECISION HISTORY
                </div>
                <table className="cb-decision-table">
                  <thead>
                    <tr>
                      <th>DATE</th>
                      <th>RATE</th>
                      <th>CHG (bps)</th>
                      <th>EXP (bps)</th>
                      <th>RESULT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cb.rate_history.map((d, i) => {
                      const sur = decisionSurprise(d.change, d.expected_change);
                      const chgBps  = Math.round(d.change * 100);
                      const expBps  = Math.round(d.expected_change * 100);
                      const chgCol  = chgBps > 0 ? 'var(--red)' : chgBps < 0 ? 'var(--green)' : 'var(--dim)';
                      return (
                        <tr key={i}>
                          <td style={{ color: 'var(--dim)', whiteSpace: 'nowrap' }}>{d.date}</td>
                          <td style={{ fontFamily: 'var(--fhead)', fontSize: '.95rem' }}>{d.rate}%</td>
                          <td style={{ color: chgCol }}>{chgBps > 0 ? '+' : ''}{chgBps}</td>
                          <td style={{ color: 'var(--dim)' }}>{expBps > 0 ? '+' : ''}{expBps}</td>
                          <td><span className={sur.cls}>{sur.label}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>

          {/* Right: auto-loaded policy rate chart */}
          <div className="card">
            <div className="ctitle" style={{ marginBottom: '.6rem', display: 'flex', justifyContent: 'space-between' }}>
              <span>POLICY RATE — 36M</span>
              {cbHistLoading && <span style={{ fontSize: '.72rem', color: 'var(--dim)' }}>Loading…</span>}
            </div>
            <div style={{ height: 260, position: 'relative' }}>
              {cbHistLoading
                ? <div style={{ color: 'var(--dim)', fontSize: '.78rem', padding: '.5rem' }}>Loading…</div>
                : cbHistory?.dates?.length > 0
                  ? <ChartCanvas buildConfig={buildCBChart(cbHistory)} deps={[cbHistory, theme]} height="100%" />
                  : <div className="chart-placeholder">NO RATE HISTORY<br />AVAILABLE</div>
              }
            </div>
          </div>
        </div>
      )}

      {/* ── Recent Releases ── */}
      <div className="slabel"><em>//</em> RECENT RELEASES — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : (
        <div className="card" style={{ marginBottom: '1.2rem', overflowX: 'auto' }}>
          <table className="cal-table">
            <thead>
              <tr><th>DATE</th><th>EVENT</th><th>PERIOD</th><th>PREV</th><th>EXP</th><th>ACTUAL</th><th>RESULT</th><th>IMPLICATION</th></tr>
            </thead>
            <tbody>
              {pastEvents.map((ev, i) => (
                <tr key={i} className="cal-past">
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--dim)' }}>{ev.date}</td>
                  <td style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.event}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem' }}>{ev.period}</td>
                  <td style={{ color: 'var(--dim)' }}>{unitStr(ev, ev.previous)}</td>
                  <td style={{ color: 'var(--dim)' }}>{unitStr(ev, ev.expected)}</td>
                  <td style={{ color: 'var(--text)', fontWeight: 600 }}>{unitStr(ev, ev.actual)}</td>
                  <td>{ev.beat_miss && <span className={`bm-tag ${BM_CLASS[ev.beat_miss] || ''}`}>{BM_LABEL[ev.beat_miss]}</span>}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem', maxWidth: 300 }}>{ev.implication}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Upcoming Releases ── */}
      <div className="slabel"><em>//</em> UPCOMING RELEASES — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem' }}>Loading…</div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="cal-table">
            <thead>
              <tr><th>DATE</th><th>EVENT</th><th>PERIOD</th><th>PREV</th><th>EXPECTED</th><th>IMPLICATION</th></tr>
            </thead>
            <tbody>
              {upcoming.map((ev, i) => (
                <tr key={i} className="cal-upcoming">
                  <td style={{ whiteSpace: 'nowrap', color: 'var(--acc)' }}>{ev.date}</td>
                  <td style={{ color: 'var(--text)', fontWeight: 500 }}>{ev.event}</td>
                  <td style={{ color: 'var(--dim)', fontSize: '.72rem' }}>{ev.period}</td>
                  <td style={{ color: 'var(--dim)' }}>{unitStr(ev, ev.previous)}</td>
                  <td style={{ color: 'var(--gold)' }}>{unitStr(ev, ev.expected)}</td>
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
