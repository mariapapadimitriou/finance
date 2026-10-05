import { useEffect, useRef, useState } from 'react';
import { categoryGradient } from '../categoryColors.js';
import { money, pct } from '../api.js';

/**
 * Categories as blocks sized by what was spent: the squarified layout, which
 * keeps blocks as close to square as it can so their areas compare honestly.
 * Each block is named on it when there is room, and every one carries its
 * name, amount and share for hover and for screen readers.
 */
export default function Treemap({ items, gap = 8 }) {
  const ref = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => {
      setSize({ w: e.contentRect.width, h: e.contentRect.height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const total = items.reduce((s, i) => s + i.value, 0);
  const rects = size.w && total > 0
    ? squarify(items.filter((i) => i.value > 0), 0, 0, size.w, size.h, total)
    : [];

  return (
    <div className="treemap" ref={ref} role="list" aria-label="Spending by category">
      {rects.map((r) => {
        const w = Math.max(r.w - gap, 0);
        const h = Math.max(r.h - gap, 0);
        const roomy = w > 90 && h > 44;
        return (
          <div key={r.item.label} className="tile-cat" role="listitem"
               title={`${r.item.label}: ${money(r.item.value)} (${pct(r.item.value / total)})`}
               aria-label={`${r.item.label}, ${money(r.item.value)}, ${pct(r.item.value / total)}`}
               style={{ left: r.x, top: r.y, width: w, height: h,
                        background: categoryGradient(r.item.label) }}>
            {roomy && <span>{r.item.label}</span>}
          </div>
        );
      })}
    </div>
  );
}

/** Squarified treemap (Bruls, Huizing & van Wijk), items largest first. */
function squarify(items, x, y, w, h, total) {
  const sorted = [...items].sort((a, b) => b.value - a.value);
  const scale = (w * h) / total;
  const out = [];
  let row = [];
  let rest = sorted.map((i) => ({ item: i, area: i.value * scale }));

  const worst = (r, side) => {
    const s = r.reduce((a, c) => a + c.area, 0);
    const max = Math.max(...r.map((c) => c.area));
    const min = Math.min(...r.map((c) => c.area));
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };

  const layout = (r) => {
    const s = r.reduce((a, c) => a + c.area, 0);
    if (w >= h) {
      const cw = s / h;
      let cy = y;
      r.forEach((c) => { const ch = c.area / cw; out.push({ ...c, x, y: cy, w: cw, h: ch }); cy += ch; });
      x += cw; w -= cw;
    } else {
      const ch = s / w;
      let cx = x;
      r.forEach((c) => { const cw = c.area / ch; out.push({ ...c, x: cx, y, w: cw, h: ch }); cx += cw; });
      y += ch; h -= ch;
    }
  };

  while (rest.length) {
    const side = Math.min(w, h);
    const next = rest[0];
    if (!row.length || worst([...row, next], side) <= worst(row, side)) {
      row.push(next);
      rest = rest.slice(1);
    } else {
      layout(row);
      row = [];
    }
  }
  if (row.length) layout(row);
  // Offset by half the gap so blocks sit evenly inside the frame.
  return out.map((r) => ({ ...r, x: r.x + 0, y: r.y + 0 }));
}
