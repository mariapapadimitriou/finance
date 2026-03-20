// Generic Chart.js wrapper for React
// Props: buildConfig(ctx) => Chart config object, deps[] controls rebuild, height
// buildConfig receives the canvas 2d context so gradient creation works
import { useEffect, useRef } from 'react';
import Chart from 'chart.js/auto';

export default function ChartCanvas({ buildConfig, deps = [], height = 260 }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    chartRef.current?.destroy();
    const cfg = buildConfig(canvasRef.current.getContext('2d'));
    if (cfg) chartRef.current = new Chart(canvasRef.current, cfg);
    return () => { chartRef.current?.destroy(); chartRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return (
    <div style={{ position: 'relative', height, width: '100%' }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
