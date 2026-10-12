import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  Breakdown, PearlProgress, ProgressBar, RangeBand, Slider, SnapshotBar,
} from './viz.jsx';
import { sliderBounds } from './vizMath.js';

const html = (el) => renderToStaticMarkup(el);

describe('ProgressBar', () => {
  it('is a progressbar with its value and a spoken label', () => {
    const out = html(<ProgressBar label="Japan trip" value="$750 of $3,000" share={0.25} />);
    expect(out).toContain('role="progressbar"');
    expect(out).toContain('aria-valuemin="0"');
    expect(out).toContain('aria-valuemax="100"');
    expect(out).toContain('aria-valuenow="25"');
    expect(out).toContain('aria-label="Japan trip, $750 of $3,000, 25 percent"');
    expect(out).toContain('width:max(var(--space-1), 25%)');
  });

  it('keeps the visible label when it names whose bar it is', () => {
    const out = html(<ProgressBar label="$100 a month" value="Ready by March" share={0.3}
                                  name="Japan" />);
    expect(out).toContain('aria-label="Japan, $100 a month, Ready by March, 30 percent"');
  });

  it('draws no fill at 0', () => {
    const out = html(<ProgressBar label="Japan trip" value="$0 of $3,000" share={0} />);
    expect(out).not.toContain('viz-fill');
    expect(out).toContain('aria-valuenow="0"');
  });

  it('turns positive once done', () => {
    expect(html(<ProgressBar label="First stop" value="$500 · done" share={1} tone="positive" />))
      .toContain('viz-fill positive');
  });
});

describe('PearlProgress', () => {
  it('words a used month without a minus, in muted text', () => {
    const out = html(<PearlProgress title="Anchor" saved={1800} target={3000} share={0.6} delta={-120} />);
    expect(out).toContain('$120 used this month');
    expect(out).toContain('viz-delta muted');
    expect(out).not.toContain('-$120');
    expect(out).toContain('$1,800 of $3,000 · 60% there');
    expect(out).toContain('--viz-share:0.6');
    expect(out).toContain('viz-fill nacre');
  });

  it('marks a good month positive, and says when nothing changed', () => {
    expect(html(<PearlProgress title="Anchor" saved={1} target={2} share={0.5} delta={300} />))
      .toContain('+$300 this month');
    expect(html(<PearlProgress title="Anchor" saved={1} target={2} share={0.5} delta={0} />))
      .toContain('No change this month');
  });
});

describe('RangeBand', () => {
  it('is hidden from screen readers and labels ten months', () => {
    const out = html(<RangeBand now="2026-10" from="2027-03" to="2027-06" />);
    expect(out).toMatch(/^<div class="viz-range" aria-hidden="true">/);
    expect((out.match(/viz-range-cell/g) ?? []).length).toBe(10);
    expect(out).toContain('>Oct<');
    expect(out).toContain('>Jul<');
  });

  it('shows no date at all with no range', () => {
    const out = html(<RangeBand now="2026-10" />);
    expect(out).not.toContain('viz-range-axis');
    expect(out).not.toMatch(/start|single/);
  });
});

describe('SnapshotBar', () => {
  const base = { category: 'Lifestyle', usualMonth: 1150, day: 12, daysInMonth: 31 };

  it('fills the action colour on pace, and says so', () => {
    const out = html(<SnapshotBar {...base} spent={445} />);
    expect(out).toContain('$445 of a usual $1,150');
    expect(out).toContain('About where you usually are');
    expect(out).toContain('class="viz-fill"');
  });

  it('turns champagne over pace, with words, never red', () => {
    const out = html(<SnapshotBar {...base} spent={700} />);
    expect(out).toContain('viz-fill over');
    expect(out).toContain('Ahead of your usual pace');
  });

  it('says how far over the month', () => {
    const out = html(<SnapshotBar {...base} spent={1290} />);
    expect(out).toContain('$140 over a usual month');
    expect(out).toContain('width:max(var(--space-1), 100%)');
  });

  it('can hide the tick, and draws nothing at 0', () => {
    const out = html(<SnapshotBar {...base} spent={0} showTick={false} />);
    expect(out).not.toContain('viz-tick');
    expect(out).not.toContain('viz-fill');
  });
});

describe('Breakdown', () => {
  it('is a list whose rows read as sentences, with the bars hidden', () => {
    const out = html(<Breakdown items={[{ name: 'Rent', amount: 1050 },
      { name: 'Groceries', amount: 450 }]} daysOfData={30} />);
    expect(out).toContain('<ul class="viz-list" aria-label="Spending by category">');
    expect((out.match(/<li /g) ?? []).length).toBe(2);
    expect(out).toContain('Rent, $1,050, 70 percent of spending');
    expect(out).toContain('Groceries, $450, 30 percent of spending');
    expect(out).toContain('<div aria-hidden="true">');
    expect(out).not.toContain('Early days');
  });

  it('says when it is early days', () => {
    expect(html(<Breakdown items={[{ name: 'Rent', amount: 10 }]} daysOfData={6} />))
      .toContain('6 days of spending');
  });

  it('is empty with nothing spent', () => {
    expect(html(<Breakdown items={[]} />)).toContain('Nothing spent yet this month.');
  });
});

describe('Slider', () => {
  it('is a native range input in $10 steps with words for its value', () => {
    const out = html(<Slider id="w" label="Put aside" value={310} bounds={sliderBounds(263)}
                             onChange={() => {}} valueText="$310 a month, about a month sooner" />);
    expect(out).toContain('type="range"');
    expect(out).toContain('min="260"');
    expect(out).toContain('max="520"');
    expect(out).toContain('step="10"');
    expect(out).toContain('aria-valuetext="$310 a month, about a month sooner"');
  });

  it('is not there when the pace is 0 or less', () => {
    expect(html(<Slider value={0} bounds={sliderBounds(0)} onChange={() => {}} />)).toBe('');
  });
});

describe('viz.css', () => {
  const css = readFileSync(new URL('./viz.css', import.meta.url), 'utf8');

  it('names no colour of its own', () => {
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g)).toBeNull();
  });

  it('rounds only with radius tokens', () => {
    const radii = [...css.matchAll(/border-radius:\s*([^;]+);/g)].map((m) => m[1]);
    expect(radii.length).toBeGreaterThan(0);
    for (const r of radii) expect(r).not.toMatch(/\d+(\.\d+)?(px|%|rem|em)/);
  });

  it('has no red', () => {
    expect(css).not.toMatch(/--(error|danger|red|border-error)/);
  });
});
