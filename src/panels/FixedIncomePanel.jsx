import { useEffect, useState } from 'react';
import ChartCanvas from '../components/ChartCanvas.jsx';
import InfoTooltip from '../components/InfoTooltip.jsx';
import {
  loadFIData,
  sortTenors,
  tooltipStyle,
  lineOpts,
  cssVar,
} from '../api.js';

const SECTION_TIPS = {
  yieldCurve: 'Government benchmark yield curve at period start (dashed gray) vs current (solid cyan). Steepening = long end rising faster than short end; flattening = the reverse. Inversion = short rates above long rates.',
  keySpreads: '2s10s = 2yr minus 10yr yield. Negative (inverted) historically signals recession within 12–18 months. 3M10Y = bill-to-bond spread — another inversion signal closely watched by the Fed.',
  tenorSnap:  'Point-in-time yield levels across all tenors at period start and end. Change column shows basis point move over the lookback period.',
  spr2s10s:   'The 2-year vs 10-year government bond spread over time in basis points. Below zero = curve inversion. Trend direction indicates whether steepening or flattening pressure is building.',
  aiAnalysis: 'AI-generated narrative using the actual spread data for this market and period. Covers curve dynamics, likely macro drivers, credit market implications, and the key risk or signal to watch.',
};

export default function FixedIncomePanel({ market, lookback, theme }) {
  const [data, setData]         = useState(null);
  const [aiText, setAiText]     = useState('');
  const [aiLoading, setAiLoading] = useState(true);
  const [error, setError]       = useState(null);

  useEffect(() => {
    setData(null);
    setAiText('');
    setAiLoading(true);
    setError(null);

    let cancelled = false;

    loadFIData(market, lookback).then(d => {
      if (cancelled) return;
      setData(d);
      runAI(d, market, lookback).then(txt => {
        if (cancelled) return;
        setAiText(txt);
        setAiLoading(false);
      });
    }).catch(err => {
      if (!cancelled) setError(err.message);
    });

    return () => { cancelled = true; };
  }, [market, lookback]);

  if (error) return <div style={{ color: 'var(--red)', fontSize: '.85rem', padding: '2rem' }}>Failed to load data: {error}<br /><span style={{ color: 'var(--dim)' }}>Is the Flask server running? → python app.py</span></div>;

  // ── Yield curve chart ────────────────────────────────────────────────────
  const buildYC = ctx => {
    if (!data) return null;
    const t = sortTenors(Object.keys(data.curve_start));
    return {
      type: 'line',
      data: {
        labels: t,
        datasets: [
          {
            label: `Start (${data.lookback}D ago)`,
            data: t.map(x => data.curve_start[x]),
            borderColor: '#2d4560',
            backgroundColor: 'rgba(45,69,96,.1)',
            borderWidth: 1.5,
            borderDash: [4, 3],
            pointRadius: 3,
            fill: true,
            tension: 0.4,
          },
          {
            label: 'Current',
            data: t.map(x => data.curve_end[x]),
            borderColor: '#00d4ff',
            backgroundColor: 'rgba(0,212,255,.07)',
            borderWidth: 2,
            pointRadius: 4,
            pointBackgroundColor: '#00d4ff',
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } } },
          ...tooltipStyle(c => `${c.dataset.label}: ${c.parsed.y.toFixed(2)}%`),
        },
        scales: {
          x: { ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 } }, grid: { color: cssVar("--chart-grid") } },
          y: { ticks: { color: cssVar("--chart-dim"), font: { family: 'IBM Plex Mono', size: 16 }, callback: v => v.toFixed(2) + '%' }, grid: { color: cssVar("--chart-grid") } },
        },
      },
    };
  };

  // ── 2s10s spread time series ─────────────────────────────────────────────
  const buildSpr2s10s = ctx => {
    if (!data) return null;
    const tsKeys = Object.keys(data.time_series);
    const ts2  = data.time_series['2Y']  || data.time_series[tsKeys[Math.floor(tsKeys.length / 2)]];
    const ts10 = data.time_series['10Y'] || data.time_series[tsKeys[tsKeys.length - 1]];
    if (!ts2 || !ts10) return null;
    const n = Math.min(ts2.dates.length, ts10.yields.length);
    const spreads = ts2.yields.slice(-n).map((y, i) => Math.round((ts10.yields[i] - y) * 100));
    const dates = ts2.dates.slice(-n);
    return {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {
            label: '2s10s',
            data: spreads,
            borderColor: '#ffd24d',
            backgroundColor: ctx2 => {
              const g = ctx2.chart.ctx.createLinearGradient(0, 0, 0, 200);
              g.addColorStop(0, 'rgba(255,210,77,.28)');
              g.addColorStop(1, 'rgba(255,210,77,0)');
              return g;
            },
            borderWidth: 2,
            fill: true,
            pointRadius: 0,
            tension: 0.35,
          },
          {
            label: 'Zero',
            data: new Array(n).fill(0),
            borderColor: 'rgba(255,61,94,.35)',
            borderWidth: 1,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: lineOpts({
        yCallback: v => v + ' bps',
        tooltipCallback: c => ` 2s10s: ${c.parsed.y} bps`,
      }),
    };
  };

  // ── Spreads grid ─────────────────────────────────────────────────────────
  const renderSpreads = () => {
    if (!data) return null;
    const sp = data.spreads;
    const bps = v => Math.round(v * 100);
    const items = [
      { lbl: '2s10s (END)',    val: bps(sp['2s10s_end']),                    delta: bps(sp['2s10s_end'] - sp['2s10s_start']) },
      { lbl: '3M10Y (END)',    val: bps(sp['3m10y_end']),                    delta: bps(sp['3m10y_end'] - sp['3m10y_start']) },
      { lbl: '2s10s Δ PERIOD',val: bps(sp['2s10s_end'] - sp['2s10s_start']),delta: null, raw: null },
      { lbl: 'SHAPE',          val: null, raw: sp.inverted ? 'INVERTED' : sp.steepening ? 'STEEPENING' : 'FLATTENING' },
    ];
    return (
      <div className="spr-grid">
        {items.map((it, idx) => {
          const inv = it.raw === 'INVERTED', steep = it.raw === 'STEEPENING';
          const vc = it.raw
            ? (inv ? 'var(--red)' : steep ? 'var(--green)' : 'var(--acc)')
            : (it.val > 0 ? 'var(--green)' : it.val < 0 ? 'var(--red)' : 'var(--text)');
          const vd = it.raw ? it.raw : `${it.val > 0 ? '+' : ''}${it.val} bps`;
          return (
            <div className="spr-cell" key={idx}>
              <div className="spr-lbl">{it.lbl}</div>
              <div className="spr-val" style={{ color: vc }}>{vd}</div>
              {it.delta !== null ? (
                <div className={`spr-delta ${it.delta > 0 ? 'pos' : it.delta < 0 ? 'neg' : ''}`}>
                  {it.delta > 0 ? '▲' : it.delta < 0 ? '▼' : '–'} {Math.abs(it.delta)} bps change
                </div>
              ) : (
                <div className="spr-delta" style={{ color: 'var(--dim)' }}>
                  {it.lbl.includes('Δ') ? 'vs period start' : 'shape'}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // ── Tenor table ──────────────────────────────────────────────────────────
  const renderTenorTable = () => {
    if (!data) return null;
    const sorted = sortTenors(Object.keys(data.curve_start));
    return (
      <table className="tenor-tbl">
        <thead>
          <tr>
            <th>TENOR</th><th>START</th><th>END</th><th>CHG</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(t => {
            const s = data.curve_start[t], e = data.curve_end[t];
            const chg = ((e - s) * 100).toFixed(1);
            return (
              <tr key={t}>
                <td style={{ color: 'var(--dim)' }}>{t}</td>
                <td>{s.toFixed(2)}%</td>
                <td>{e.toFixed(2)}%</td>
                <td className={parseFloat(chg) > 0 ? 'tup' : 'tdn'}>{chg > 0 ? '+' : ''}{chg}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  };

  return (
    <>
      {/* ── Yield curve + Spreads + Tenor table ── */}
      <div className="g-fi">
        <div className="card">
          <div className="ctitle">YIELD CURVE — START VS END <InfoTooltip text={SECTION_TIPS.yieldCurve} /></div>
          {data && (
            <ChartCanvas buildConfig={buildYC} deps={[data, market, lookback, theme]} height={300} />
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.8rem' }}>
          <div className="card">
            <div className="ctitle">KEY SPREADS (BPS) <InfoTooltip text={SECTION_TIPS.keySpreads} /></div>
            {renderSpreads()}
          </div>
          <div className="card">
            <div className="ctitle">TENOR SNAPSHOT <InfoTooltip text={SECTION_TIPS.tenorSnap} /></div>
            {renderTenorTable()}
          </div>
        </div>
      </div>

      {/* ── 2s10s time series ── */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="ctitle">2s10s SPREAD — TIME SERIES (BPS) <InfoTooltip text={SECTION_TIPS.spr2s10s} /></div>
        {data && (
          <ChartCanvas buildConfig={buildSpr2s10s} deps={[data, market, lookback, theme]} height={190} />
        )}
      </div>

      {/* ── AI Curve Analysis ── */}
      <div className="slabel"><em>//</em> AI CURVE ANALYSIS <InfoTooltip text={SECTION_TIPS.aiAnalysis} /></div>
      <div className="ai-box">
        <div className="ai-hdr">
          <div className="aidot" />
          YIELD CURVE ANALYSIS
        </div>
        <div className={`ai-txt${aiLoading ? ' loading' : ''}`} style={{ whiteSpace: 'pre-wrap' }}>
          {aiText}
        </div>
      </div>
    </>
  );
}

// ── Curve analysis (procedural) ───────────────────────────────────────────────
function runAI(d, market, lookback) {
  const sp = d.spreads;
  const bps = v => Math.round(v * 100);
  const dir = sp.steepening ? 'steepened' : 'flattened';
  const chg = Math.abs(bps(sp['2s10s_end'] - sp['2s10s_start']));

  return Promise.resolve(`The ${market} government yield curve has ${dir} by ${chg} basis points over the past ${lookback} trading days, with the 2s10s spread moving from ${bps(sp['2s10s_start'])} to ${bps(sp['2s10s_end'])} bps.${sp.inverted ? ' The curve remains inverted — a condition historically associated with recession risk over a 12–18 month horizon.' : ''}

${sp.steepening
  ? 'The steepening dynamic reflects term premium expansion, as investors demand greater compensation for holding longer-duration paper amid uncertainty around the inflation trajectory and fiscal supply. The front end remains anchored by central bank guidance, while the long end reprices the neutral rate higher.'
  : 'The flattening move suggests either a defensive rotation into long-duration bonds — consistent with fading growth expectations — or continued front-end pressure from policy rates staying elevated longer. Bull flattening typically signals markets pricing in a growth slowdown ahead.'}

For credit markets, ${sp['2s10s_end'] < 0
  ? 'the inverted curve historically foreshadows tighter credit conditions and rising defaults over the medium term, particularly affecting floating-rate borrowers and leveraged credits'
  : 'the curve shape implies cautious risk appetite; monitor IG and HY spread widening as an early stress signal'}. Rate-sensitive sectors — utilities, REITs, long-duration growth equities — face headwinds if the long end continues to rise.

Watch for the next central bank meeting and CPI print as the key catalysts that could force a significant repricing across the entire curve.`);
}
