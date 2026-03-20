import { useEffect, useState } from 'react';
import { loadSummaryData } from '../api.js';

const REGIME_CLASS = { CALM: 'calm', LOW: 'low', MODERATE: 'moderate', HIGH: 'high', EXTREME: 'extreme' };
const SHAPE_COLOR  = { INVERTED: 'var(--red)', FLAT: 'var(--gold)', NORMAL: 'var(--acc)', STEEP: 'var(--green)' };

export default function RegimeSummaryBar({ market }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    setData(null);
    let cancelled = false;
    loadSummaryData(market)
      .then(d => { if (!cancelled) setData(d); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [market]);

  if (!data) {
    return (
      <div className="regime-bar">
        <div className="rb-inner" style={{ color: 'var(--dim)', fontSize: '.7rem' }}>
          Loading regime data…
        </div>
      </div>
    );
  }

  const rc = REGIME_CLASS[data.regime] || 'moderate';
  const curveColor = SHAPE_COLOR[data.yield_curve_shape] || 'var(--text)';
  const bpsStr = data.yield_curve_bps >= 0 ? `+${data.yield_curve_bps}` : `${data.yield_curve_bps}`;

  return (
    <div className="regime-bar">
      <div className="rb-inner">

        {/* Difficulty */}
        <div className="rb-group">
          <span className="rb-lbl">DIFFICULTY</span>
          <span className={`rb-regime regime-${rc}`}>
            {data.regime} {Math.round(data.difficulty_score)}
          </span>
        </div>

        <div className="rb-sep" />

        {/* Yield curve */}
        <div className="rb-group">
          <span className="rb-lbl">CURVE</span>
          <span className="rb-val" style={{ color: curveColor }}>
            {data.yield_curve_shape}
          </span>
          <span className="rb-sub">{bpsStr} bps</span>
        </div>

        <div className="rb-sep" />

        {/* Top sector */}
        <div className="rb-group">
          <span className="rb-lbl">LEADING</span>
          <span className="rb-val pos">{data.top_sector}</span>
          <span className="rb-sub pos">+{data.top_sector_return?.toFixed(1)}%</span>
        </div>

        <div className="rb-sep" />

        {/* Bottom sector */}
        <div className="rb-group">
          <span className="rb-lbl">LAGGING</span>
          <span className="rb-val neg">{data.bottom_sector}</span>
          <span className="rb-sub neg">{data.bottom_sector_return?.toFixed(1)}%</span>
        </div>

        <div className="rb-sep" />

        {/* Dominant factor */}
        <div className="rb-group" style={{ maxWidth: 280 }}>
          <span className="rb-lbl">DOMINANT FACTOR</span>
          <span className="rb-val" style={{ color: 'var(--purple)' }}>{data.dominant_factor_regime}</span>
          <span className="rb-sub" style={{ color: 'var(--dim)' }}>
            {data.dominant_factor} ({data.dominant_factor_spread >= 0 ? '+' : ''}{data.dominant_factor_spread?.toFixed(1)}%)
          </span>
        </div>

      </div>
    </div>
  );
}
