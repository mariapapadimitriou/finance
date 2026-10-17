import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import FlowCards, { chartWords, linePath, scaleTop } from './FlowCards.jsx';
import { dayParts } from './TransactionsList.jsx';

const html = (el) => renderToStaticMarkup(el);
const flows = {
  month: '2026-10', days: 31, upto: 9,
  out: [40, 65, 65, 120, 180, 220, 316, 316, 359],
  in: [2150, 2150, 2150, 2150, 2150, 2150, 2150, 2150, 2150],
  usual: { months: 3, out: Array.from({ length: 31 }, (_, i) => 60 * (i + 1)),
           in: Array.from({ length: 31 }, (_, i) => (i < 14 ? 2150 : 4300)) },
};

describe('Outflows and Inflows (ALT-04)', () => {
  it('two cards: outflows signed in red, inflows signed in green, each with its line', () => {
    const out = html(<FlowCards totals={{ spent: 3144.34, income: 2150 }} flows={flows} />);
    expect(out).toContain('Outflows');
    expect(out).toContain('Inflows');
    expect(out).toContain('fc-figure out">-$3,144.34');
    expect(out).toContain('fc-figure in">+$2,150.00');
    expect(out).toContain('class="fc-now"');
    expect(out).toContain('class="fc-usual"');
    expect(out).toContain('fc-dot');
    expect(out).not.toContain('Moving');
    expect(out).not.toContain('Transfer');
  });

  it('with no single month there are figures and no lines', () => {
    const out = html(<FlowCards totals={{ spent: 10, income: 0 }} flows={null} />);
    expect(out).toContain('-$10.00');
    expect(out).toContain('$0.00');
    expect(out).not.toContain('fc-chart');
  });

  it('a screen reader hears where the month stands', () => {
    expect(chartWords('out', flows)).toBe('$359.00 so far; usually $540.00 by now.');
    expect(chartWords('in', { ...flows, usual: null })).toBe('$2,150.00 so far.');
  });

  it('inflows step, outflows slope, and the scale fits both lines', () => {
    expect(linePath([0, 10], 2, 10, true)).toContain(' H300.0 V');
    expect(linePath([0, 10], 2, 10)).toContain(' L300.0 ');
    expect(scaleTop([1, 2], [5])).toBeCloseTo(5.4);
  });
});

describe('Day headers (ALT-04): a name and a date, no totals', () => {
  const now = new Date(2026, 9, 9);
  it('Today, Yesterday, the weekday within a week, then the date', () => {
    expect(dayParts('2026-10-09', now)).toEqual({ name: 'Today', date: 'Fri, Oct 9' });
    expect(dayParts('2026-10-08', now)).toEqual({ name: 'Yesterday', date: 'Thu, Oct 8' });
    expect(dayParts('2026-10-07', now)).toEqual({ name: 'Wednesday', date: 'Oct 7' });
    expect(dayParts('2026-10-01', now)).toEqual({ name: 'October 1', date: 'Thursday' });
    expect(dayParts('2025-12-24', now)).toEqual({ name: 'December 24, 2025', date: 'Wednesday' });
  });
});
