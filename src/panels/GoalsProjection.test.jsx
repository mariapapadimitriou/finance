import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HowWorkedOut, ProjectionPage, rangeSheet } from './GoalsProjection.jsx';
import { projection } from '../pearl/vizMath.js';

// P-01's Anchor in October: $5,470 of $8,700, August left out as unusual.
// Each month is what the Anchor grew by: put away, less what the chests took.
const pace = {
  used: [{ month: '2026-06', saved: 230 }, { month: '2026-07', saved: 360 },
         { month: '2026-09', saved: 160 }],
  best: { month: '2026-07', saved: 360 },
  quietest: { month: '2026-09', saved: 160 },
  usual: 250,
  left_out: [{ month: '2026-08', saved: -120 }],
};
const goals = {
  month: '2026-10',
  anchor: {
    started: true, earned: false, target: 8700, counted: 5470, to_go: 3230, pace, chests_monthly: 400,
    projection: projection(3230, pace, '2026-10'),
    counting: [{ account_id: 'td', name: 'TD Savings', mask: '8820', balance: 1320 },
               { account_id: 'tg', name: 'Tangerine Savings', mask: '0932', balance: 6100 }],
  },
};

describe('How we worked this out, for the range (P-02)', () => {
  const sheet = rangeSheet(goals);

  it('lays the rows out as P-02: still to go, the months, best, quietest, usual, left out', () => {
    expect(sheet.title).toBe('Your Anchor date');
    expect(sheet.rows.map((r) => [r.label, r.display])).toEqual([
      ['Still to go', '$3,230'],
      ['Months used', 'June, July, September'],
      ['Best month · July', '+$360 to your Anchor'],
      ['Quietest month · September', '+$160 to your Anchor'],
      ['Your usual pace', '$250 a month'],
      ['Left out', 'August, marked unusual'],
    ]);
    expect(sheet.rows[5].lines[0]).toEqual({ label: 'August', display: '$120 out of it' });
    expect(sheet.total.label).toBe('Likely there');
    expect(sheet.total.display).toBe('July 2027 to July 2028');
    expect(sheet.note).toContain('We use your best and quietest months for the range');
  });

  it('the range runs from the best month to the quietest', () => {
    const p = goals.anchor.projection;
    expect(p.state).toBe('range');
    expect(p.from < p.to).toBe(true);
  });

  it('draws the sheet with the what-if and months links, and Got it', () => {
    const out = renderToStaticMarkup(<HowWorkedOut goals={goals} onClose={() => {}} />);
    expect(out).toContain('How we worked this out');
    expect(out).toContain('Want it sooner? Try a different monthly amount');
    expect(out).toContain('Change which months count');
    expect(out).toMatch(/pk-btn primary[^>]*>Got it/);
    expect(out).not.toMatch(/Protect|Build|Unveil|Shine/);
  });
});

describe('When you’ll reach 3 months (P-01, P-05)', () => {
  it('says how the Anchor grows, less what the chests take', () => {
    const out = renderToStaticMarkup(<ProjectionPage goals={goals} onBack={() => {}} onHow={() => {}}
                                                     onWhatIf={() => {}} onMonths={() => {}} onTab={() => {}} />);
    for (const text of ['When you’ll reach 3 months', 'Likely there',
                        'Your Anchor grows by what you put away, less the $400 a month your chests take.',
                        'From June, July and September: $160 to $360 a month. Interest isn’t included.',
                        '1 month left out: you marked', 'August', '$5,470 of $8,700 · $3,230 to go',
                        'Back to your Anchor']) {
      expect(out).toContain(text);
    }
  });

  it('no date when more has gone out than come in', () => {
    const none = { ...goals, anchor: { ...goals.anchor, projection: { state: 'none', reason: 'no_pace', subscriptions_monthly: 64 } } };
    const out = renderToStaticMarkup(<ProjectionPage goals={none} onBack={() => {}} onHow={() => {}}
                                                     onWhatIf={() => {}} onMonths={() => {}} onTab={() => {}} />);
    for (const text of ['No date yet', 'Lately, more has gone out than come in',
                        'A date wouldn’t be honest right now. As soon as you save a little, we’ll show a range again.',
                        'One thing that could help', 'Your subscriptions cost $64 a month', 'See the suggestion']) {
      expect(out).toContain(text);
    }
  });
});
