import { useEffect, useState } from 'react';
import {
  loadInflationData, loadCentralBanksData, loadCalendarData, loadSummaryData,
  loadIndicatorHistory, cssVar,
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
const BIAS_CLASS    = { HOLD: 'bias-hold', EASING: 'bias-easing', TIGHTENING: 'bias-tightening' };
const TREND_ICON    = { UP: '↑', DOWN: '↓', FLAT: '→' };
const TREND_COLOR   = { UP: 'var(--red)', DOWN: 'var(--green)', FLAT: 'var(--gold)' };
const BM_CLASS      = { BEAT: 'bm-beat', MISS: 'bm-miss', INLINE: 'bm-inline' };
const BM_LABEL      = { BEAT: 'BEAT', MISS: 'MISS', INLINE: 'IN LINE' };

// ─────────────────────────────────────────────────────────────────────────────
export default function MacroPanel({ market, theme }) {
  const [summary, setSummary]     = useState(null);
  const [inflation, setInflation] = useState(null);
  const [cb, setCb]               = useState(null);
  const [calendar, setCalendar]   = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const [selectedIndicator, setSelectedIndicator] = useState(null); // { ticker, label, unit }
  const [indicatorHistory, setIndicatorHistory]   = useState(null);
  const [histLoading, setHistLoading]             = useState(false);

  useEffect(() => {
    setLoading(true);
    setSummary(null); setInflation(null); setCb(null); setCalendar(null);
    setError(null);
    setSelectedIndicator(null);

    Promise.all([
      loadSummaryData(market),
      loadInflationData(market),
      loadCentralBanksData(market),
      loadCalendarData(market),
    ]).then(([sum, infl, cbData, cal]) => {
      setSummary(sum);
      setInflation(infl);
      setCb(cbData);
      setCalendar(cal);
      setLoading(false);
    }).catch(err => { setError(err.message); setLoading(false); });
  }, [market]);

  useEffect(() => {
    if (!selectedIndicator) { setIndicatorHistory(null); return; }
    setHistLoading(true);
    loadIndicatorHistory(selectedIndicator.ticker, 36)
      .then(d => { setIndicatorHistory(d); setHistLoading(false); })
      .catch(() => setHistLoading(false));
  }, [selectedIndicator]);

  const handleSelectIndicator = (ticker, label, unit) => {
    setSelectedIndicator(prev =>
      prev?.ticker === ticker ? null : { ticker, label, unit }
    );
  };

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
            backgroundColor: bg,
            borderColor: dim,
            borderWidth: 1,
            titleColor: dim,
            bodyColor: text,
            titleFont: { family: 'IBM Plex Mono', size: 13 },
            bodyFont:  { family: 'IBM Plex Mono', size: 14 },
            callbacks: { label: ctx => ` ${ctx.parsed.y.toFixed(2)}${indicator.unit}` },
          },
        },
        scales: {
          x: {
            ticks: { color: dim, font: { family: 'IBM Plex Mono', size: 12 }, maxTicksLimit: 9 },
            grid:  { color: grid },
          },
          y: {
            ticks: {
              color: dim,
              font: { family: 'IBM Plex Mono', size: 12 },
              callback: v => `${parseFloat(v).toFixed(1)}${indicator.unit}`,
            },
            grid: { color: grid },
          },
        },
      },
    };
  };

  const note         = buildNote(summary, calendar);
  const pastEvents   = calendar?.events.filter(e => e.status === 'PAST').reverse()   || [];
  const upcoming     = calendar?.events.filter(e => e.status === 'UPCOMING')          || [];
  const dateLabel    = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).toUpperCase();

  const unitStr = (ev, val) => val == null ? '—' :
    `${val}${ev.unit !== 'K' && ev.unit !== 'index' ? ev.unit : ev.unit === 'K' ? 'K' : ''}`;

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

      {/* ── Indicator History Chart ── */}
      {selectedIndicator && (
        <>
          <div className="slabel" style={{ display: 'flex', alignItems: 'center', gap: '.8rem' }}>
            <span><em>//</em> {selectedIndicator.label.toUpperCase()} — 36 MONTH HISTORY</span>
            <button
              onClick={() => setSelectedIndicator(null)}
              style={{ background: 'none', border: '1px solid var(--border2)', color: 'var(--dim)',
                       cursor: 'pointer', fontSize: '.68rem', padding: '.15rem .5rem', borderRadius: 2,
                       fontFamily: 'var(--fmono)', letterSpacing: '.05em' }}
            >✕ CLOSE</button>
          </div>
          <div className="card" style={{ marginBottom: '1.2rem' }}>
            <div style={{ height: 200, position: 'relative' }}>
              {histLoading ? (
                <div style={{ color: 'var(--dim)', fontSize: '.8rem', padding: '.5rem' }}>Loading…</div>
              ) : indicatorHistory?.dates?.length > 0 ? (
                <ChartCanvas
                  buildConfig={buildHistoryChart(indicatorHistory, selectedIndicator)}
                  deps={[indicatorHistory, selectedIndicator, theme]}
                  height="100%"
                />
              ) : (
                <div style={{ color: 'var(--dim)', fontSize: '.8rem', padding: '.5rem' }}>No data available</div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Inflation Dashboard ── */}
      <div className="slabel"><em>//</em> INFLATION — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : (
        <div className="g4" style={{ marginBottom: '1.2rem' }}>
          {inflation?.readings.map((r, i) => (
            <div
              className="card"
              key={i}
              onClick={() => r.ticker && handleSelectIndicator(r.ticker, r.label, r.unit)}
              style={{
                cursor: r.ticker ? 'pointer' : undefined,
                borderColor: selectedIndicator?.ticker === r.ticker ? 'var(--acc)' : undefined,
                transition: 'border-color .15s',
              }}
            >
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

      {/* ── Central Bank ── */}
      <div className="slabel"><em>//</em> CENTRAL BANK — {market}</div>
      {loading ? (
        <div style={{ color: 'var(--dim)', fontSize: '.8rem', marginBottom: '1.2rem' }}>Loading…</div>
      ) : cb && (
        <div
          className="card"
          style={{
            marginBottom: '1.2rem',
            borderColor: selectedIndicator?.ticker === cb.rate_ticker ? 'var(--acc)' : undefined,
            transition: 'border-color .15s',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '2rem', flexWrap: 'wrap' }}>
            <div
              onClick={() => cb.rate_ticker && handleSelectIndicator(cb.rate_ticker, `${cb.bank} Policy Rate`, '%')}
              style={{ cursor: cb.rate_ticker ? 'pointer' : undefined }}
            >
              <div className="ctitle" style={{ marginBottom: '.5rem' }}>{cb.bank}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem', marginBottom: '.5rem' }}>
                <span style={{ fontFamily: 'var(--fhead)', fontSize: '2.8rem', lineHeight: 1, color: 'var(--text)' }}>
                  {cb.policy_rate}
                </span>
                <span style={{ fontSize: '.85rem', color: 'var(--dim)' }}>%</span>
                <span style={{ fontSize: '.85rem', marginLeft: '.4rem',
                  color: cb.last_change > 0 ? 'var(--red)' : cb.last_change < 0 ? 'var(--green)' : 'var(--dim)' }}>
                  ({cb.last_change > 0 ? '+' : ''}{(cb.last_change * 100) | 0}bps last move)
                </span>
              </div>
              <div style={{ marginBottom: '.6rem' }}>
                <span className={`cb-bias ${BIAS_CLASS[cb.bias] || 'bias-hold'}`}>{cb.bias}</span>
              </div>
              <div style={{ fontSize: '.78rem', color: 'var(--dim)' }}>
                Last change: <span style={{ color: 'var(--text)' }}>{cb.last_change_date}</span>
                <span style={{ margin: '0 .8rem', color: 'var(--border2)' }}>|</span>
                Next meeting: <span style={{ color: 'var(--acc)' }}>{cb.next_meeting}</span>
              </div>
            </div>
            <div style={{ flex: 1, minWidth: 280, fontSize: '.82rem', color: 'var(--dim)', lineHeight: 1.8,
              borderLeft: '2px solid var(--border2)', paddingLeft: '1.2rem', marginTop: '.2rem' }}>
              {cb.bias_note}
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
