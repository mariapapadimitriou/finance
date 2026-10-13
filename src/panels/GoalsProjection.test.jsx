import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HowWorkedOut, anchorSheet } from './GoalsProjection.jsx';
import { projection } from '../pearl/vizMath.js';

// P-01's Anchor in October: $620 of $2,150, August left out as unusual.
const pace = {
  used: [{ month: '2026-09', saved: 180 }, { month: '2026-07', saved: 340 },
         { month: '2026-06', saved: 260 }],
  best: { month: '2026-07', saved: 340 },
  quietest: { month: '2026-09', saved: 180 },
  usual: 260,
  left_out: [{ month: '2026-08', saved: -120 }],
};
const goals = {
  month: '2026-10',
  anchor: {
    target: 2150, counted: 620, to_go: 1530, pace,
    projection: projection(1530, pace, '2026-10'),
    counting: [{ account_id: 'eq', name: 'EQ Bank Savings', balance: 520 },
               { account_id: 'ws', name: 'Wealthsimple Cash', balance: 100 }],
  },
};

describe('How we worked this out, for the Anchor (X-03, P-02)', () => {
  const sheet = anchorSheet(goals);

  it('answers with the range, as P-02 does', () => {
    expect(sheet.title).toBe('Likely full between March and July 2027');
    expect(sheet.sub).toBe('If you keep saving like you do now.');
    expect(sheet.note).toContain('Your best month (July) and your quietest (September) give the range');
  });

  it('lays the rows out as X-03: goal, saved, left, each month', () => {
    expect(sheet.rows.map((r) => [r.label, r.display])).toEqual([
      ['Your goal', '$2,150.00'],
      ['Already saved', '$620.00'],
      ['Left to save', '$1,530.00'],
      ['You add each month', '$260.00'],
    ]);
    expect(sheet.rows[1].detail).toBe('In EQ Bank Savings and Wealthsimple Cash');
    expect(sheet.rows[3].detail).toBe('Your usual amount over September, July and June');
  });

  it('adds up: the goal less what’s saved is what’s left', () => {
    const [goal, saved, left] = sheet.rows;
    expect(goals.anchor.target - goals.anchor.counted).toBe(goals.anchor.to_go);
    expect([goal, saved, left].every((r) => r.display.startsWith('$'))).toBe(true);
  });

  it('counts the months to go at her usual pace, from next month', () => {
    expect(sheet.total).toEqual({
      label: 'Months to go', detail: 'Starting from November', display: '6 → April 2027' });
  });

  it('opens each month, the left-out one marked', () => {
    expect(sheet.rows[3].lines.map((l) => `${l.label}: ${l.display}`)).toEqual([
      'September · quietest month: $180 saved',
      'July · best month: $340 saved',
      'June: $260 saved',
      'August · left out, marked unusual: $120 taken out',
    ]);
  });

  it('one month for the whole range says so', () => {
    const one = { ...goals, anchor: { ...goals.anchor,
                                       projection: { state: 'range', from: '2027-04', to: '2027-04' } } };
    expect(anchorSheet(one).title).toBe('Likely full in April 2027');
  });

  it('draws the sheet with the what-if and months links, and Got it', () => {
    const out = renderToStaticMarkup(<HowWorkedOut goals={goals} onClose={() => {}} />);
    expect(out).toContain('How we worked this out');
    expect(out).toContain('Want it sooner? Try a different monthly amount');
    expect(out).toContain('Change which months count');
    expect(out).toMatch(/pk-btn primary[^>]*>Got it/);
    expect(out).toContain('6 → April 2027');
  });
});
