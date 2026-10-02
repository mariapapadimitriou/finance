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
