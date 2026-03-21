import { useEffect, useState } from 'react';
import ChartCanvas from '../components/ChartCanvas.jsx';
import InfoTooltip from '../components/InfoTooltip.jsx';
import {
  loadDifficultyData,
  COMP_COLORS,
  tooltipStyle,
  cssVar,
} from '../api.js';

const SECTION_TIPS = {
  timeSeries:  'Composite score (0–100) blending 13 normalized market stress indicators. Threshold lines at 40 (MODERATE), 60 (HIGH), 75 (EXTREME). Higher score = harder to execute trades cleanly.',
  components:  'Each component normalized to its own lookback range: 0 = period low, 100 = period high. Bar length shows relative stress vs the period. Weighted contribution drives the composite.',
  scoreRing:   'Weighted composite of all 13 components. Score of 75+ historically correlates with elevated realized slippage, wider bid-ask spreads, and reduced price discovery efficiency.',
  radar:       'Current component scores (red) vs their period averages (gray). Asymmetric shape highlights which factors are driving the regime above or below normal — useful for diagnosing the stress source.',
};

const COMP_TIPS = {
  VIX:          'CBOE Volatility Index. 30-day implied vol of S&P 500 options. The primary fear gauge — spikes sharply in dislocations. Carries the highest single weight (22%) in the composite.',
  VVIX:         'Volatility of the VIX itself. Elevated VVIX signals uncertainty about uncertainty — historically precedes sudden vol regime shifts and is a leading indicator of VIX spikes.',
  PutCall:      'Equity put/call volume ratio. High ratio = extreme hedging demand. Contrarian signal at extremes, but confirms stress when elevated alongside other components.',
  HYSpread:     'High-yield credit spread over Treasuries (OAS). Widening propagates from credit to equities. The most capital-intensive stress signal — second highest weight (13%).',
  TED:          'Treasury-Eurodollar spread. Bank funding stress proxy. Elevated TED = dealers pulling market-making capital, which widens bid-ask spreads across asset classes.',
  SkewIndex:    'CBOE SKEW Index. Measures tail-risk pricing in out-of-the-money options. High SKEW = market paying elevated premium for crash protection.',
  CorrelBreak:  'Cross-asset correlation breakdown index. High score = correlations are unstable — hedges are unreliable and cross-asset diversification breaks down.',
  ATR_SPX:      'Average True Range of S&P 500. Measures intraday price swing. High ATR = elevated slippage risk on entries and difficulty sizing positions consistently.',
  RealizedVol:  '20-day realized volatility annualized. Backward-looking confirmation. Validates whether implied vol (VIX) is justified by actual price action.',
  BidAskProxy:  'Bid-ask spread proxy index. Direct measure of execution cost. Spikes when liquidity providers withdraw — effectively a symptom of the other stress components.',
  Dispersion:   'CBOE Dispersion Index. High dispersion = stock-specific risk dominates macro. Broad index positioning becomes unreliable; selection risk is elevated.',
  FundingStress:'Short-rate funding dislocation (1Y SOFR proxy). Elevated = funding costs impair leveraged positioning and can force involuntary position liquidations.',
  BreadthDecay: 'Market breadth proxy (advance/decline). Narrow rallies driven by few stocks signal fragile conditions with elevated reversal and whipsaw risk.',
};

export default function DifficultyPanel({ market, lookback, theme }) {
  const [data, setData]   = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    let cancelled = false;
    loadDifficultyData(market, lookback).then(d => {
      if (!cancelled) setData(d);
    }).catch(err => {
      if (!cancelled) setError(err.message);
    });
    return () => { cancelled = true; };
  }, [market, lookback]);

  if (error) return <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>Failed to load data: {error}<br /><span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span></div>;

  // ── Composite difficulty chart ───────────────────────────────────────────
  const buildDiffChart = ctx => {
    if (!data) return null;
    const grad = ctx.createLinearGradient(0, 0, 0, 220);
    grad.addColorStop(0, 'rgba(255,61,94,.3)');
    grad.addColorStop(0.5, 'rgba(255,210,77,.15)');
    grad.addColorStop(1, 'rgba(61,255,160,0)');

    const n = data.composite.length;
    return {
      type: 'line',
      data: {
        labels: data.dates,
        datasets: [
          {
            label: 'Difficulty Score',
            data: data.composite,
            borderColor: ctx2 => {
              const g = ctx2.chart.ctx.createLinearGradient(0, 0, ctx2.chart.width, 0);
              g.addColorStop(0, '#3dffa0');
              g.addColorStop(0.4, '#ffd24d');
              g.addColorStop(0.7, '#ff8c42');
              g.addColorStop(1, '#ff3d5e');
              return g;
            },
            backgroundColor: grad,
            borderWidth: 2.5,
            pointRadius: 0,
            fill: true,
            tension: 0.35,
          },
          {
            label: 'HIGH',
            data: new Array(n).fill(60),
            borderColor: 'rgba(255,140,66,.3)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
          {
            label: 'MODERATE',
            data: new Array(n).fill(40),
            borderColor: 'rgba(255,210,77,.25)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
          {
            label: 'EXTREME',
            data: new Array(n).fill(75),
            borderColor: 'rgba(255,61,94,.35)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          ...tooltipStyle(c => c.dataset.label === 'Difficulty Score' ? ` Score: ${c.parsed.y}` : null),
        },
        scales: {
          x: {
            ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 }, maxTicksLimit: 7 },
            grid: { color: cssVar("--chart-grid") },
          },
          y: {
            min: 0,
            max: 100,
            ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 }, stepSize: 25, callback: v => v },
            grid: { color: cssVar("--chart-grid") },
          },
        },
      },
    };
  };

  // ── Radar chart ──────────────────────────────────────────────────────────
  const buildRadar = ctx => {
    if (!data) return null;
    const comps = data.components;
    const labels = Object.values(comps).map(c => c.label);
    const latest = Object.values(comps).map(c => c.normalized[c.normalized.length - 1] || 0);
    const avg = Object.values(comps).map(c => {
      const n = c.normalized;
      return n.length ? n.reduce((a, b) => a + b, 0) / n.length : 0;
    });
    return {
      type: 'radar',
      data: {
        labels,
        datasets: [
          {
            label: 'Period Avg',
            data: avg,
            borderColor: 'rgba(74,104,128,.7)',
            backgroundColor: 'rgba(74,104,128,.1)',
            borderWidth: 1.5,
            pointRadius: 3,
            pointBackgroundColor: 'rgba(74,104,128,.7)',
          },
          {
            label: 'Current',
            data: latest,
            borderColor: '#ff3d5e',
            backgroundColor: 'rgba(255,61,94,.15)',
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#ff3d5e',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } } },
          ...tooltipStyle(c => ` ${c.label}: ${c.parsed.r.toFixed(1)}`),
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 }, backdropColor: 'transparent', stepSize: 25 },
            grid: { color: 'rgba(23,34,48,.8)' },
            pointLabels: { color: cssVar("--chart-text"), font: { family: 'IBM Plex Mono', size: 16 } },
            angleLines: { color: 'rgba(23,34,48,.8)' },
          },
        },
      },
    };
  };

  // ── Score ring ───────────────────────────────────────────────────────────
  const renderScoreRing = () => {
    if (!data) return null;
    const s = data.summary;
    const cur = s.current_score;
    const vc = cur >= 75 ? 'var(--red)' : cur >= 60 ? 'var(--orange)' : cur >= 40 ? 'var(--gold)' : cur >= 25 ? 'var(--acc)' : 'var(--green)';
    const rmap = { CALM: 'calm', LOW: 'low', MODERATE: 'moderate', HIGH: 'high', EXTREME: 'extreme' };
    return (
      <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '.6rem', padding: '1.4rem 1rem' }}>
        <div className="ctitle" style={{ width: '100%', textAlign: 'center', marginBottom: 0, justifyContent: 'center' }}>
          CURRENT DIFFICULTY SCORE <InfoTooltip text={SECTION_TIPS.scoreRing} />
        </div>
        <div className="diff-score-ring" style={{ borderColor: vc, boxShadow: `0 0 20px ${vc}44` }}>
          <div className="diff-score-val" style={{ color: vc }}>{Math.round(cur)}</div>
          <div className="diff-score-lbl">/ 100</div>
        </div>
        <div className={`diff-regime regime-${rmap[s.regime] || 'moderate'}`}>{s.regime}</div>
        <div style={{ fontSize: '.62rem', color: 'var(--dim)', textAlign: 'center' }}>
          <div>Period avg: <span style={{ color: 'var(--text)' }}>{s.avg_score.toFixed(1)}</span></div>
          <div>Pctl vs period: <span style={{ color: 'var(--text)' }}>{s.percentile}</span>th</div>
        </div>
      </div>
    );
  };

  // ── Component grid ───────────────────────────────────────────────────────
  const renderCompGrid = () => {
    if (!data) return null;
    return Object.entries(data.components).map(([key, c]) => {
      const nv = c.normalized[c.normalized.length - 1] || 0;
      const col = COMP_COLORS[key] || 'var(--acc)';
      return (
        <div className="comp-row" key={key}>
          <div className="comp-name" style={{ display: 'flex', alignItems: 'center' }}>
            {c.label} <InfoTooltip text={COMP_TIPS[key] || ''} direction="above" />
          </div>
          <div className="comp-track">
            <div className="comp-fill" style={{ width: `${nv}%`, background: col }} />
          </div>
          <div className="comp-val" style={{ color: col }}>{Math.round(nv)}</div>
        </div>
      );
    });
  };

  // ── Equation box ─────────────────────────────────────────────────────────
  const renderEqBox = () => {
    if (!data) return null;
    const parts = data.equation.split('·');
    return (
      <div className="eq-box">
        <div style={{ color: 'var(--acc)', fontSize: '.6rem', letterSpacing: '.1em', marginBottom: '.4rem' }}>COMPOSITE EQUATION</div>
        {parts.map((part, i) => (
          <span key={i}>{i === 0 ? <strong>{part}</strong> : part}{i < parts.length - 1 ? '·' : ''}</span>
        ))}
      </div>
    );
  };

  return (
    <>
      <div className="g-diff">
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="card">
            <div className="ctitle">TRADING DIFFICULTY INDEX — TIME SERIES <InfoTooltip text={SECTION_TIPS.timeSeries} /></div>
            {data && (
              <ChartCanvas buildConfig={buildDiffChart} deps={[data, market, lookback, theme]} height={220} />
            )}
          </div>
          <div className="card">
            <div className="ctitle">COMPONENT CONTRIBUTIONS <InfoTooltip text={SECTION_TIPS.components} /></div>
            <div className="comp-grid">
              {renderCompGrid()}
            </div>
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {renderScoreRing()}

          <div className="card">
            <div className="ctitle">REGIME GUIDE</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '.4rem', fontSize: '.62rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--green)' }}>● CALM</span>
                <span style={{ color: 'var(--dim)' }}>0–25: Low vol, tight spreads, clear price discovery</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--acc)' }}>● LOW</span>
                <span style={{ color: 'var(--dim)' }}>25–40: Normal conditions, manageable risk</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--gold)' }}>● MODERATE</span>
                <span style={{ color: 'var(--dim)' }}>40–60: Elevated vol, watch sizing</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--orange)' }}>● HIGH</span>
                <span style={{ color: 'var(--dim)' }}>60–75: Wide spreads, slippage risk high</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--red)' }}>● EXTREME</span>
                <span style={{ color: 'var(--dim)' }}>75+: Crisis-like, execution severely impaired</span>
              </div>
            </div>
          </div>

          {renderEqBox()}
        </div>
      </div>

      {/* ── Component Breakdown Radar ── */}
      <div className="slabel"><em>//</em> COMPONENT BREAKDOWN CHART</div>
      <div className="card">
        <div className="ctitle">ALL COMPONENTS — NORMALIZED (0–100) <InfoTooltip text={SECTION_TIPS.radar} /></div>
        {data && (
          <ChartCanvas buildConfig={buildRadar} deps={[data, market, lookback, theme]} height={240} />
        )}
      </div>
    </>
  );
}
