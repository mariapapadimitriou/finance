import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  CalendarStrip, ComingUp, DayBody, MonthGrid, Totals, cellWords, dueAmount,
} from './CalendarPanel.jsx';

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};

const cell = (date, day, state, due = [], inMonth = true) => ({ date, day, in_month: inMonth, state, due });
const october = {
  month: '2026-10', label: 'October 2026', today: '2026-10-09', this_month: true,
  prev: { month: '2026-09', label: 'September' }, next: { month: '2026-11', label: 'November' },
  totals: { spent: 3144.34, income: 2150, moving: 654.5, so_far: true },
  cells: [
    cell('2026-09-27', 27, 'outside', [], false), cell('2026-09-28', 28, 'outside', [], false),
    cell('2026-09-29', 29, 'outside', [], false), cell('2026-09-30', 30, 'outside', [], false),
    cell('2026-10-01', 1, 'on'), cell('2026-10-02', 2, 'on'), cell('2026-10-03', 3, 'on'),
    cell('2026-10-04', 4, 'on'), cell('2026-10-05', 5, 'on'), cell('2026-10-06', 6, 'ahead'),
    cell('2026-10-07', 7, 'ahead'), cell('2026-10-08', 8, 'ahead'), cell('2026-10-09', 9, 'today'),
    cell('2026-10-10', 10, 'future'),
    ...Array.from({ length: 21 }, (_, k) => cell(`2026-10-${String(11 + k).padStart(2, '0')}`, 11 + k, 'future',
      11 + k === 15 ? [{ kind: 'bill', label: 'Netflix', amount: 16.49, date: '2026-10-15' }]
        : 11 + k === 16 ? [{ kind: 'pay', label: 'Pay', amount: 2150, date: '2026-10-16' }] : [])),
    cell('2026-11-01', 1, 'future', [{ kind: 'bill', label: 'Rent', amount: 1450, date: '2026-11-01' },
      { kind: 'chest', label: 'Japan trip from Anchor', amount: 250, date: '2026-11-01' }], false),
    ...Array.from({ length: 6 }, (_, k) => cell(`2026-11-0${2 + k}`, 2 + k, 'future', [], false)),
  ],
  has_usual: true,
  coming_up: [{ kind: 'bill', label: 'Netflix', amount: 16.49, date: '2026-10-15' },
              { kind: 'pay', label: 'Pay', amount: 2150, date: '2026-10-16' },
              { kind: 'bill', label: 'Rent', amount: 1450, date: '2026-11-01' }],
  legend: [{ key: 'on', label: 'On or under your usual pace by the end of the day' },
           { key: 'ahead', label: 'Spending moved ahead of your usual pace' },
           { key: 'none', label: 'No data yet' }, { key: 'today', label: 'Today' }],
};

describe('Calendar (CAL-01)', () => {
  it('draws the month Sunday first with shaded past days, markers, today, and what is due', () => {
    const out = html(<MonthGrid data={october} onPrev={noop} onNext={noop} onDay={noop} />);
    expect(out).toContain('October 2026');
    expect(out).toContain('September');
    expect(out).toContain('November');
    expect(out.indexOf('>Sun<')).toBeLessThan(out.indexOf('>Mon<'));
    expect(out).toContain('class="cal-cell on"');
    expect(out).toContain('class="cal-cell ahead"');
    expect(out).toContain('class="cal-cell today"');
    expect(out).toContain('cal-cell outside');
    expect(out).toContain('cal-mark on');
    expect(out).toContain('cal-mark ahead');
    expect(out).toContain('Netflix');
    expect(out).toContain('-$16.49');
    expect(out).toContain('+$2,150.00');
    expect(out).toContain('Japan trip from Anchor');
    expect(out).toContain('cal-due-item chest');
    expect(out).toContain('No data yet');
    expect(out.toLowerCase()).not.toContain('bad');
  });

  it('a cell says its state and what is due, never a spent amount', () => {
    expect(cellWords(cell('2026-10-06', 6, 'ahead'))).toBe('6, spending moved ahead of your usual pace');
    expect(cellWords(cell('2026-10-01', 1, 'on'))).toBe('1, on or under your usual pace');
    expect(cellWords(cell('2026-10-15', 15, 'future', [{ kind: 'bill', label: 'Netflix', amount: 16.49 }])))
      .toBe('15, Netflix -$16.49');
    expect(cellWords(cell('2026-09-27', 27, 'outside', [], false))).toBe('Sep 27');
    expect(dueAmount({ kind: 'chest', amount: 250 })).toBe('$250');
  });

  it('totals say so far this month', () => {
    const out = html(<Totals totals={october.totals} />);
    expect(out).toContain('Spent so far');
    expect(out).toContain('$3,144.34');
    expect(out).toContain('Moving money');
    const past = html(<Totals totals={{ ...october.totals, so_far: false }} />);
    expect(past).toContain('>Spent<');
  });

  it('coming up lists what is due with its day (CAL-05)', () => {
    const out = html(<ComingUp items={october.coming_up} />);
    expect(out).toContain('Coming up');
    expect(out).toContain('Oct 15');
    expect(out).toContain('Nov 1');
    expect(html(<ComingUp items={[]} />)).toContain('Nothing due before the month ends.');
  });
});

describe('A day (CAL-02, CAL-03)', () => {
  it('a past day shows what was spent, what was due, and why it is shaded', () => {
    const d = { date: '2026-10-07', label: 'Wednesday, October 7', state: 'ahead', past: true, today: false,
                reason: 'Spending moved ahead of your usual pace after this day, mostly from one IKEA purchase.',
                spent: [{ id: 'a', merchant: 'IKEA', category: 'Shopping', unusual: true, amount: 289 },
                        { id: 'b', merchant: 'Loblaws', category: 'Groceries', unusual: false, amount: 96.32 }],
                spent_total: 385.32, due: [] };
    const out = html(<DayBody d={d} onClose={noop} onTransactions={noop} />);
    expect(out).toContain('Wednesday, October 7');
    expect(out).toContain('mostly from one IKEA purchase');
    expect(out).toContain('Shopping · unusual');
    expect(out).toContain('-$289.00');
    expect(out).toContain('Nothing was due.');
    expect(out).toContain('See these transactions');
  });

  it('an upcoming day shows only what is due', () => {
    const d = { date: '2026-10-16', label: 'Friday, October 16', state: 'future', past: false, today: false,
                reason: 'Upcoming days only show what’s due. Safe to spend already counts these.',
                spent: [], spent_total: 0,
                due: [{ kind: 'pay', label: 'Pay', amount: 2150, note: 'Northwind Labs · expected' },
                      { kind: 'bill', label: 'Netflix', amount: 16.49, note: 'Usually the 15th' }] };
    const out = html(<DayBody d={d} onClose={noop} onTransactions={noop} />);
    expect(out).toContain('Northwind Labs · expected');
    expect(out).toContain('+$2,150.00');
    expect(out).not.toContain('>Spent<');
    expect(out).toContain('>Done<');
  });
});

describe('The strip on Home (CAL-06)', () => {
  it('one tiny cell per day, a dot where something is due, and the line', () => {
    const strip = { month: '2026-10', label: 'October',
                    cells: [{ date: '2026-10-01', day: 1, state: 'on', due: false },
                            { date: '2026-10-06', day: 6, state: 'ahead', due: false },
                            { date: '2026-10-09', day: 9, state: 'today', due: false },
                            { date: '2026-10-15', day: 15, state: 'future', due: true }],
                    line: 'Next: Netflix on Oct 15, then pay on Oct 16. Spending moved ahead of your usual pace on Oct 6.' };
    const out = html(<CalendarStrip strip={strip} onOpen={noop} />);
    expect(out).toContain('>October<');
    expect(out).toContain('Open calendar');
    expect(out).toContain('cal-mini on');
    expect(out).toContain('cal-mini ahead');
    expect(out).toContain('cal-mini today');
    expect(out).toContain('cal-mini future has-due');
    expect(out).toContain('Spending moved ahead of your usual pace on Oct 6.');
    expect(html(<CalendarStrip strip={null} onOpen={noop} />)).toBe('');
  });
});
