import { describe, expect, it } from 'vitest';
import {
  addMonths, breakdownRows, breakdownWords, deltaWords, fillPercent, fillWidth, monthsTo,
  paceFraction, paceNote, paceStatus, pearlSize, percentWords, progressLabel, projection,
  rangeCells, roundHalfEven, sliderBounds, sliderKey, sliderPercent, sliderWords, snapshotFill,
  soonerWords, whatIf,
} from './vizMath.js';

describe('fills', () => {
  it('uses the exact percentage, capped to 0–100', () => {
    expect(fillPercent(0.613)).toBeCloseTo(61.3);
    expect(fillPercent(1.4)).toBe(100);
    expect(fillPercent(-0.2)).toBe(0);
    expect(fillPercent(undefined)).toBe(0);
    expect(fillPercent(NaN)).toBe(0);
  });

  it('draws nothing at exactly 0 and at least 4px above it', () => {
    expect(fillWidth(0)).toBeNull();
    expect(fillWidth(-3)).toBeNull();
    expect(fillWidth(0.2)).toBe('max(var(--space-1), 0.2%)');
    expect(fillWidth(61.3)).toBe('max(var(--space-1), 61.3%)');
    expect(fillWidth(140)).toBe('max(var(--space-1), 100%)');
  });

  it('never says 0 percent once started, nor 100 before done', () => {
    expect(percentWords(0)).toBe(0);
    expect(percentWords(0.3)).toBe(1);
    expect(percentWords(42.5)).toBe(43);
    expect(percentWords(99.6)).toBe(99);
    expect(percentWords(100)).toBe(100);
  });

  it('labels the bar "label, value, N percent"', () => {
    expect(progressLabel('Emergency fund', '$3,600 of $6,000', 60))
      .toBe('Emergency fund, $3,600 of $6,000, 60 percent');
  });

  it('grows the pearl from 16px to 40px', () => {
    expect(pearlSize(0)).toBe(16);
    expect(pearlSize(50)).toBe(28);
    expect(pearlSize(100)).toBe(40);
    expect(pearlSize(150)).toBe(40);
  });

  it('words the month without a minus', () => {
    expect(deltaWords(300)).toEqual({ tone: 'positive', text: '+$300 this month' });
    expect(deltaWords(-120)).toEqual({ tone: 'muted', text: '$120 used this month' });
    expect(deltaWords(0)).toEqual({ tone: 'muted', text: 'No change this month' });
  });
});

describe('snapshot', () => {
  it('follows her own curve with 3 months of history', () => {
    expect(paceFraction({ usualByToday: 400, usualMonth: 1000, day: 10, daysInMonth: 31,
      monthsOfHistory: 3 })).toBeCloseTo(0.4);
  });

  it('falls back to the day of the month under 3 months', () => {
    expect(paceFraction({ usualByToday: 400, usualMonth: 1000, day: 15, daysInMonth: 30,
      monthsOfHistory: 2 })).toBeCloseTo(0.5);
    expect(paceFraction({ usualMonth: 1000, day: 15, daysInMonth: 30, monthsOfHistory: 5 }))
      .toBeCloseTo(0.5);
  });

  it('fills spent ÷ usual, capped at a full bar', () => {
    expect(snapshotFill(0, 1000)).toBe(0);
    expect(snapshotFill(412, 1150)).toBeCloseTo(0.3583, 3);
    expect(snapshotFill(1290, 1150)).toBe(1);
  });

  it('is on pace within ±10% of her usual by today', () => {
    expect(paceStatus(110, 100, 1000)).toBe('on');
    expect(paceStatus(90, 100, 1000)).toBe('on');
    expect(paceStatus(89, 100, 1000)).toBe('under');
    expect(paceStatus(111, 100, 1000)).toBe('over');
    expect(paceStatus(0, 0, 1000)).toBe('on');
  });

  it('is over the month once spent passes a usual month', () => {
    expect(paceStatus(1290, 1000, 1150)).toBe('over-month');
    expect(paceStatus(1150, 1000, 1150)).toBe('over');
  });

  it('says each status in words', () => {
    expect(paceNote('on')).toBe('About where you usually are');
    expect(paceNote('under')).toBe('A little under your usual pace');
    expect(paceNote('over')).toBe('Ahead of your usual pace');
    expect(paceNote('over-month', 1290, 1150)).toBe('$140 over a usual month');
  });
});

describe('range cells', () => {
  const states = (cells) => cells.map((c) => c.state[0]).join('');

  it('runs ten months from this one', () => {
    const cells = rangeCells('2026-10', '2027-03', '2027-06');
    expect(cells.map((c) => c.month)[0]).toBe('2026-10');
    expect(cells.at(-1).month).toBe('2027-07');
    expect(states(cells)).toBe('ooooosmmeo');
  });

  it('fills one cell for a one-month range', () => {
    expect(states(rangeCells('2026-10', '2026-12', '2026-12'))).toBe('oosooooooo');
  });

  it('runs to the edge when the range ends past the axis', () => {
    expect(states(rangeCells('2026-10', '2027-05', '2028-01'))).toBe('ooooooosme');
  });

  it('fills only the last month when the whole range is past the axis', () => {
    expect(states(rangeCells('2026-10', '2027-11', '2028-03'))).toBe('ooooooooos');
  });

  it('is all empty with no range', () => {
    expect(states(rangeCells('2026-10', null, null))).toBe('oooooooooo');
  });

  it('crosses the year', () => {
    expect(addMonths('2026-11', 3)).toBe('2027-02');
    expect(addMonths('2026-12', 1)).toBe('2027-01');
  });
});

describe('breakdown', () => {
  const cats = [
    { name: 'Rent', amount: 1050 }, { name: 'Groceries', amount: 412 },
    { name: 'Dining out', amount: 214 }, { name: 'Transit', amount: 120 },
    { name: 'Phone', amount: 80 }, { name: 'Books', amount: 60 },
    { name: 'Gifts', amount: 40 }, { name: 'Nothing', amount: 0 },
  ];

  it('keeps the top five then Everything else (n)', () => {
    const rows = breakdownRows(cats);
    expect(rows.map((r) => r.name)).toEqual(
      ['Rent', 'Groceries', 'Dining out', 'Transit', 'Phone', 'Everything else (2)']);
    expect(rows.at(-1).amount).toBe(100);
  });

  it('scales bars to the largest row', () => {
    const rows = breakdownRows(cats);
    expect(rows[0].bar).toBe(1);
    expect(rows[1].bar).toBeCloseTo(412 / 1050);
  });

  it('adds shares to 100, the rounding going to Everything else', () => {
    const rows = breakdownRows([
      { name: 'A', amount: 1 }, { name: 'B', amount: 1 }, { name: 'C', amount: 1 },
      { name: 'D', amount: 1 }, { name: 'E', amount: 1 }, { name: 'F', amount: 1 },
    ]);
    expect(rows.reduce((t, r) => t + r.share, 0)).toBe(100);
    expect(rows.slice(0, 5).map((r) => r.share)).toEqual([17, 17, 17, 17, 17]);
    expect(rows.at(-1).share).toBe(15);
  });

  it('gives the rounding to the largest with five or fewer', () => {
    const rows = breakdownRows([{ name: 'A', amount: 2 }, { name: 'B', amount: 1 },
      { name: 'C', amount: 1 }, { name: 'D', amount: 1 }, { name: 'E', amount: 1 }]);
    expect(rows.map((r) => r.share)).toEqual([32, 17, 17, 17, 17]);
    const three = breakdownRows([{ name: 'A', amount: 1 }, { name: 'B', amount: 1 },
      { name: 'C', amount: 1 }]);
    expect(three.map((r) => r.share)).toEqual([34, 33, 33]);
  });

  it('is empty with nothing spent', () => {
    expect(breakdownRows([])).toEqual([]);
    expect(breakdownRows([{ name: 'A', amount: 0 }])).toEqual([]);
  });

  it('reads as a sentence', () => {
    expect(breakdownWords({ name: 'Groceries', amount: 412, share: 20 }))
      .toBe('Groceries, $412, 20 percent of spending');
  });
});

describe('slider', () => {
  it('starts at the usual pace rounded to $10 and goes to about double', () => {
    expect(sliderBounds(263)).toEqual({ min: 260, start: 260, max: 520, step: 10 });
    expect(sliderBounds(265)).toMatchObject({ start: 270 });
    expect(sliderBounds(3)).toMatchObject({ start: 10, max: 20 });
  });

  it('has no slider at a pace of 0 or less', () => {
    expect(sliderBounds(0)).toBeNull();
    expect(sliderBounds(-40)).toBeNull();
    expect(sliderBounds(undefined)).toBeNull();
  });

  it('moves $10 on arrows and $50 on Page Up/Down, within bounds', () => {
    const b = { min: 260, max: 520 };
    expect(sliderKey('ArrowRight', 300, b)).toBe(310);
    expect(sliderKey('ArrowUp', 300, b)).toBe(310);
    expect(sliderKey('ArrowLeft', 300, b)).toBe(290);
    expect(sliderKey('ArrowDown', 300, b)).toBe(290);
    expect(sliderKey('PageUp', 300, b)).toBe(350);
    expect(sliderKey('PageDown', 300, b)).toBe(260);
    expect(sliderKey('PageUp', 500, b)).toBe(520);
    expect(sliderKey('Home', 400, b)).toBe(260);
    expect(sliderKey('End', 400, b)).toBe(520);
    expect(sliderKey('a', 400, b)).toBeNull();
  });

  it('places the knob along the track', () => {
    expect(sliderPercent(260, { min: 260, max: 520 })).toBe(0);
    expect(sliderPercent(390, { min: 260, max: 520 })).toBe(50);
    expect(sliderPercent(520, { min: 260, max: 520 })).toBe(100);
  });

  it('says the value and what it does in words', () => {
    expect(sliderWords(310, { projection: { state: 'range' }, sooner: 1 }))
      .toBe('$310 a month, about a month sooner');
    expect(sliderWords(260, { projection: { state: 'range' }, sooner: 0 }))
      .toBe('$260 a month, about the same time');
    expect(sliderWords(260, { projection: { state: 'none' }, sooner: null }))
      .toBe('$260 a month, still no date');
    expect(soonerWords(3)).toBe('About 3 months sooner');
  });
});

describe('projection on the device (finance/anchor.py)', () => {
  const pace = { best: { saved: 600 }, quietest: { saved: 200 }, usual: 400 };

  it('rounds halves to even, as Python does', () => {
    expect(roundHalfEven(0.5)).toBe(0);
    expect(roundHalfEven(1.5)).toBe(2);
    expect(roundHalfEven(2.5)).toBe(2);
    expect(roundHalfEven(-1.5)).toBe(-2);
    expect(roundHalfEven(1.4)).toBe(1);
  });

  it('counts whole months, or never', () => {
    expect(monthsTo(0, 100)).toBe(0);
    expect(monthsTo(1000, 0)).toBeNull();
    expect(monthsTo(1000, 300)).toBe(4);
    expect(monthsTo(900, 300)).toBe(3);
  });

  it('gives a range from the best month to the quietest', () => {
    expect(projection(2400, pace, '2026-10')).toEqual({
      state: 'range', from: '2027-02', to: '2027-10', low: 200, high: 600, usual: 400 });
  });

  it('is full, or honestly no date', () => {
    expect(projection(0, pace, '2026-10')).toEqual({ state: 'full' });
    expect(projection(100, null, '2026-10')).toEqual({ state: 'none', reason: 'no_history' });
    expect(projection(100, { best: { saved: 50 }, quietest: { saved: -300 }, usual: -10 },
      '2026-10')).toEqual({ state: 'none', reason: 'no_pace' });
  });

  it('falls back to the usual pace when the quietest month saved nothing', () => {
    const p = projection(1200, { best: { saved: 600 }, quietest: { saved: -100 }, usual: 300 },
      '2026-10');
    expect(p).toMatchObject({ from: '2026-12', to: '2027-02' });
  });

  it('measures sooner between the middles of the two ranges', () => {
    const now = '2026-10';
    const current = projection(2400, pace, now);
    const r = whatIf({ toGo: 2400, pace, now, current }, 500);
    expect(r.extra).toBe(100);
    expect(r.projection).toMatchObject({ from: '2027-02', to: '2027-06' });
    // middles: (Feb+Oct)/2 vs (Feb+Jun)/2, two months apart
    expect(r.sooner).toBe(2);
    expect(whatIf({ toGo: 2400, pace, now, current }, 400).sooner).toBe(0);
  });
});
