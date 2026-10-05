// Chart.js configuration.
//
// Both charts here plot a single measure over time, so each carries one series
// in the first categorical slot and needs no legend — the card title names it.
// Marks stay thin, gridlines are solid hairlines one shade off the surface, and
// every chart ships a tooltip, since a chart on a web page is interactive by
// default.

import { money, cssVar, monthLabel, dateLabel } from './api.js';

function ink() {
  return {
    series: cssVar('--series-1'),
    series3: cssVar('--series-3'),
    series3Soft: cssVar('--series-3-soft'),
    soft: cssVar('--series-1-soft'),
    grid: cssVar('--grid'),
    axis: cssVar('--axis'),
    muted: cssVar('--muted'),
    text: cssVar('--ink'),
    text2: cssVar('--ink-2'),
    surface: cssVar('--surface'),
    border: cssVar('--border-firm'),
  };
}

function tooltip(c, labelFn) {
  return {
    backgroundColor: c.surface,
    borderColor: c.border,
    borderWidth: 1,
    titleColor: c.text2,
    bodyColor: c.text,
    titleFont: { family: 'system-ui', size: 12, weight: '500' },
    bodyFont: { family: 'system-ui', size: 14, weight: '600' },
    padding: 10,
    displayColors: false,
    callbacks: labelFn,
  };
}

const AXIS_FONT = { family: 'system-ui', size: 11 };

/** Monthly spend, as a line. One series, crosshair-style index tooltip. */
export function monthlyTrendConfig(monthly) {
  const c = ink();
  const labels = monthly.map((m) => m.month);
  const values = monthly.map((m) => m.spend);

  return {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: c.series,
        backgroundColor: c.soft,
        borderWidth: 2,
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        // A 2px ring in the surface colour separates the hovered point from
        // the line beneath it without drawing a border around the mark.
        pointHoverBorderColor: c.surface,
        pointHoverBackgroundColor: c.series,
        pointHitRadius: 16,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // No entry animation: these redraw on every filter and theme change, and
      // a growing line adds nothing to a number you are trying to read.
      animation: false,
      // Bigger hit target than the mark: hovering anywhere in the column works.
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltip(c, {
          title: (items) => monthLabel(items[0].label, { long: true }),
          label: (ctx) => money(ctx.parsed.y, { cents: true }),
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0, autoSkipPadding: 12,
            callback(i) { return monthLabel(this.getLabelForValue(i)); },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * Cumulative savings under two scenarios.
 *
 * The only two-series chart in the app, and it earns the second series: the gap
 * between the lines *is* the message. Slots 1 and 3 of the validated set, which
 * are the furthest apart of the three under every simulated colour vision
 * deficiency — and both lines are named in a direct legend beside their end
 * values, so the hues are reinforcement rather than the only key.
 *
 * The area between them is filled, because the found cuts are usually small
 * beside the surplus and two bare strokes at that ratio read as one line. The
 * band doesn't exaggerate the gap — it is exactly the gap — it just gives it a
 * shape you can see at a glance instead of a second stroke you can't.
 */
export function projectionConfig(series) {
  const c = ink();
  const line = (data, color) => ({
    data,
    borderColor: color,
    borderWidth: 2,
    fill: false,
    tension: 0.25,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 2,
    pointHoverBorderColor: c.surface,
    pointHoverBackgroundColor: color,
    pointHitRadius: 16,
  });

  return {
    type: 'line',
    data: {
      labels: series.map((r) => r.month),
      datasets: [
        {
          ...line(series.map((r) => r.on_plan), c.series3),
          label: 'Following the plan',
          // Fill between the two lines rather than down to the axis: the gap
          // is the point, and either line can be the higher one — spend under
          // budget and your recent pace beats the plan.
          fill: { target: 1, above: c.series3Soft, below: c.soft },
        },
        { ...line(series.map((r) => r.pace), c.series), label: 'Recent pace' },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltip(c, {
          title: (items) => `Month ${items[0].label}`,
          label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}`,
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0,
            callback(i) { return `M${this.getLabelForValue(i)}`; },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/** Daily spend for the trailing window, as thin bars with rounded data-ends. */
export function dailySpendConfig(daily) {
  const c = ink();
  return {
    type: 'bar',
    data: {
      labels: daily.map((d) => d.date),
      datasets: [{
        data: daily.map((d) => d.amount),
        backgroundColor: c.series,
        borderRadius: 3,
        borderSkipped: false,
        barPercentage: 0.9,
        categoryPercentage: 0.92,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltip(c, {
          title: (items) => dateLabel(items[0].label),
          label: (ctx) => money(ctx.parsed.y, { cents: true }),
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0, autoSkip: true,
            maxTicksLimit: 8,
            callback(i) { return dateLabel(this.getLabelForValue(i)); },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 4,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * Contributions against what they are worth, year by year.
 *
 * Two lines with the area between them filled, because that area is the only
 * thing this chart is for: the lower line is money she put in, the upper one
 * is what it grew to, and the gap is the growth. Drawing value alone would
 * flatter it — a big number with no sense of how much of it was simply saved.
 */
export function investedConfig(series) {
  const c = ink();
  const line = (data, color) => ({
    data,
    borderColor: color,
    borderWidth: 2,
    fill: false,
    tension: 0.25,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 2,
    pointHoverBorderColor: c.surface,
    pointHoverBackgroundColor: color,
    pointHitRadius: 16,
  });

  return {
    type: 'line',
    data: {
      labels: series.map((r) => r.year),
      datasets: [
        {
          ...line(series.map((r) => r.value), c.series3),
          label: 'What it is worth',
          fill: { target: 1, above: c.series3Soft, below: c.soft },
        },
        {
          ...line(series.map((r) => r.contributed), c.series),
          label: 'What you put in',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltip(c, {
          title: (items) => (items[0].label === '1' ? 'After 1 year'
            : `After ${items[0].label} years`),
          label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}`,
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0,
            // Every fifth year, so thirty labels do not become a smear.
            callback(i) {
              const y = Number(this.getLabelForValue(i));
              return y % 5 === 0 ? `${y}y` : '';
            },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * Where each year's mortgage payments go: principal and interest, stacked.
 *
 * One measure (dollars paid in a year), so one axis — the balance owing is a
 * different scale and lives in the tooltip and the figures beside the chart,
 * never on a second axis. Slots 1 and 3, the validated pair the projection
 * uses, with a legend beside the chart so the hues are never the only key.
 * Interest sits at the bottom, where the early years make it tall: the
 * crossover, when principal overtakes it, is the shape worth seeing.
 */
export function mortgageConfig(byYear) {
  const c = ink();
  const bar = (data, color, label, top) => ({
    label,
    data,
    backgroundColor: color,
    // A 2px surface gap between the stacked segments and adjacent bars.
    borderColor: c.surface,
    borderWidth: { top: 2, left: 1, right: 1, bottom: 0 },
    borderRadius: top ? { topLeft: 4, topRight: 4 } : 0,
    borderSkipped: false,
    maxBarThickness: 22,
    stack: 'paid',
  });

  return {
    type: 'bar',
    data: {
      labels: byYear.map((r) => r.year),
      datasets: [
        bar(byYear.map((r) => r.interest), c.series3, 'Interest', false),
        bar(byYear.map((r) => r.principal), c.series, 'Principal', true),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltip(c, {
          title: (items) => {
            const row = byYear[items[0].dataIndex];
            return `Year ${row.year} · to ${monthLabel(row.ending)}`;
          },
          label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}`,
          footer: (items) => `Owing after: ${money(byYear[items[0].dataIndex].balance)}`,
          }),
          // Two series in one tooltip, so each value carries its swatch.
          displayColors: true,
          boxPadding: 4,
          footerColor: c.text2,
          footerFont: { family: 'system-ui', size: 12, weight: '500' },
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0,
            callback(i) {
              const y = Number(this.getLabelForValue(i));
              return y === 1 || y % 5 === 0 ? `${y}y` : '';
            },
          },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * Invest or pay down: how far ahead investing is, year by year.
 *
 * The two worlds' net worth would be two lines a few thousand dollars apart
 * on a half-million-dollar scale — indistinguishable. Their difference is the
 * answer, so that is the one series drawn, against a zero line: above it
 * investing is ahead, below it paying down is.
 */
export function investOrPayDownConfig(series) {
  const c = ink();
  const gap = series.map((r) => Math.round(r.invest - r.prepay));
  return {
    type: 'line',
    data: {
      labels: series.map((r) => r.year),
      datasets: [{
        data: gap,
        borderColor: c.series,
        borderWidth: 2,
        fill: { target: { value: 0 }, above: c.soft, below: c.series3Soft },
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        pointHoverBorderColor: c.surface,
        pointHoverBackgroundColor: c.series,
        pointHitRadius: 16,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltip(c, {
          title: (items) => `By ${monthLabel(series[items[0].dataIndex].month, { long: true })}`,
          label: (ctx) => (ctx.parsed.y >= 0
            ? `Investing ahead by ${money(ctx.parsed.y)}`
            : `Paying down ahead by ${money(-ctx.parsed.y)}`),
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0,
            callback(i) {
              const y = Number(this.getLabelForValue(i));
              return Number.isInteger(y) && y % 5 === 0 ? `${y}y` : '';
            },
          },
        },
        y: {
          grid: {
            // The zero line is the verdict's dividing line, so it is the one
            // gridline drawn firmly.
            color: (ctx) => (ctx.tick.value === 0 ? c.axis : c.grid),
            drawTicks: false,
          },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * CoastFIRE: what is needed to coast at each age, against what you will have.
 *
 * Both in today's dollars on one axis. "Needed" rises to the FIRE number at
 * retirement — it is that number discounted back to each age — and where the
 * investments line crosses it is the coast age. Slots 3 and 1, the validated
 * pair, named in the legend beside the chart.
 */
export function coastConfig(series) {
  const c = ink();
  const line = (data, color, label, dashed = false) => ({
    label,
    data,
    borderColor: color,
    borderWidth: 2,
    borderDash: dashed ? [6, 4] : [],
    fill: false,
    tension: 0.25,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 2,
    pointHoverBorderColor: c.surface,
    pointHoverBackgroundColor: color,
    pointHitRadius: 16,
  });

  return {
    type: 'line',
    data: {
      labels: series.map((r) => r.age),
      datasets: [
        line(series.map((r) => r.invested), c.series, 'Your investments'),
        // Dashed as well as a different hue, so the target reads as a target
        // without relying on colour.
        line(series.map((r) => r.needed), c.series3, 'Needed to coast', true),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltip(c, {
            title: (items) => `At ${Math.floor(Number(items[0].label))}`,
            label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}`,
          }),
          displayColors: true,
          boxPadding: 4,
        },
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: c.axis },
          ticks: {
            color: c.muted, font: AXIS_FONT, maxRotation: 0,
            callback(i) {
              const age = Math.floor(Number(this.getLabelForValue(i)));
              return age % 5 === 0 ? String(age) : '';
            },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: c.grid, drawTicks: false },
          border: { display: false },
          ticks: {
            color: c.muted, font: AXIS_FONT, padding: 8, maxTicksLimit: 5,
            callback: (v) => money(v),
          },
        },
      },
    },
  };
}

/**
 * This month's running total over a usual month's.
 *
 * One measure, one axis. The usual month is grey with a faint fill — the
 * ground this month is read against — and this month is the brand colour,
 * ending in a dot at today. No gridlines or axis labels: the totals above
 * the chart say the numbers, and the tooltip gives any day.
 */
export function paceConfig(pace) {
  const c = ink();
  const baseline = cssVar('--baseline');
  const baselineSoft = cssVar('--baseline-soft');
  const days = Array.from({ length: pace.days }, (_, i) => i + 1);
  const thisMonth = days.map((d) => (d <= pace.through ? pace.this[d - 1] : null));
  const last = pace.through - 1;

  return {
    type: 'line',
    data: {
      labels: days,
      datasets: [
        {
          label: 'This month',
          data: thisMonth,
          borderColor: c.series,
          borderWidth: 3,
          tension: 0.35,
          fill: false,
          pointRadius: (ctx) => (ctx.dataIndex === last ? 6 : 0),
          pointBackgroundColor: c.series,
          pointBorderColor: c.series,
          pointHoverRadius: 6,
          pointHitRadius: 14,
          spanGaps: false,
        },
        {
          label: 'Usual month',
          data: pace.average,
          borderColor: baseline,
          backgroundColor: baselineSoft,
          borderWidth: 2,
          tension: 0.35,
          fill: 'origin',
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHitRadius: 14,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8, right: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltip(c, {
            title: (items) => `Day ${items[0].label}`,
            label: (ctx) => (ctx.parsed.y == null ? null
              : `${ctx.dataset.label}: ${money(ctx.parsed.y)}`),
          }),
          displayColors: true,
          boxPadding: 4,
        },
      },
      scales: {
        x: { display: false },
        y: { display: false, beginAtZero: true },
      },
    },
  };
}
