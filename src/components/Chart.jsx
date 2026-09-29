import { useEffect, useRef } from 'react';
import ChartJS from 'chart.js/auto';

/**
 * A Chart.js canvas.
 *
 * `theme` is a dependency because chart colours are read from CSS custom
 * properties at config time — a theme switch has to rebuild the chart, not
 * just re-render the component around it.
 */
export default function Chart({ config, theme, ariaLabel }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current || !config) return undefined;

    chartRef.current = new ChartJS(canvasRef.current, config);
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [config, theme]);

  return <canvas ref={canvasRef} role="img" aria-label={ariaLabel} />;
}
