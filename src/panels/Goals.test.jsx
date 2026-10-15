import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { GrowInto, Overview, calculatorWords, learnWords, projectionWords } from './Goals.jsx';

// THL-248 (design THL-240 SV-P01, SV-P03): Save is the Anchor, then treasure
// chests, then "What this could grow into" — three illustrative cards and the
// rates footnote. Someone new sees no projection card until the Anchor is set
// up; the calculator and Learn are always open. No product names.

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const NAMES = /Protect|Build|Unveil|Shine|Growth/;

const anchor = {
  started: true, earned: false, full: false, dipped: false, counted: 5470, savings: 7420, chests: 1950,
  usual: 2900, months: 1.9, target: 8700, to_go: 3230, share: 0.6287, saved_this_month: 200,
  chests_monthly: 400, accounts: ['td'], counting: [], available_accounts: [], recent: [],
  pace: { usual: 250, used: [], left_out: [], best: { month: '2026-07', saved: 360 }, quietest: { month: '2026-09', saved: 160 } },
  projection: { state: 'range', from: '2027-07', to: '2028-06' }, pace_months: [], unusual: [],
  suggestion: { months: [], average: 2900, amount: 2900, target: 8700 },
};
const goals = { month: '2026-10', phase: 'build', anchor, chests: [], chest_suggestion: null,
                spend_categories: [], bank_funded: [], saving_goal: { set: false }, safe_to_spend: 642 };
const learn = { read: 2, of: 5, next: 'risk-time-horizon',
                modules: [{ id: 'tfsa-rrsp-fhsa', done: true }, { id: 'index-funds-etfs', done: true }] };
const noop = () => {};

describe('Save (SV-P01)', () => {
  it('Anchor, chests, then what this could grow into, in that order', () => {
    const out = html(<Overview goals={goals} learn={learn} onTab={noop} onStart={noop} onAnchor={noop}
                               onProjection={noop} onWhatIf={noop} onNewChest={noop} onChest={noop} />);
    const at = (s) => out.indexOf(s);
    expect(at('Your Anchor')).toBeGreaterThan(0);
    expect(at('Treasure chests')).toBeGreaterThan(at('Your Anchor'));
    expect(at('What this could grow into')).toBeGreaterThan(at('Treasure chests'));
    for (const s of ['>Save</h1>', 'Illustrative, to help you plan. Pearl never recommends a product.',
                     'When your Anchor reaches 3 months', 'Jul 2027 – Jun 2028',
                     'Growing about $250 a month: what you put away, less what your chests take.',
                     'Try putting away more', 'What regular investing could grow to', '$13,970 – $17,310',
                     '$100 a month for 10 years ($12,000 put in), at illustrative 3% to 7% a year.',
                     'Open the calculator', 'Learn at your pace', '2 of 5 read',
                     'Next: Risk and time horizon · 4 min', 'Keep learning',
                     'Illustrative rates of 3%, 5% and 7% a year, added monthly, before fees and taxes.']) {
      expect(out).toContain(s);
    }
    expect(out).not.toContain('class="in-tabs"');
    expect(out).not.toContain('Saving goal');
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
  });

  it('someone new (SV-P03): no projection card until the Anchor is set up; the rest is open', () => {
    const fresh = { ...goals, phase: 'protect', anchor: { ...anchor, started: false, counted: 0, months: null } };
    const out = html(<GrowInto goals={fresh} learn={{ read: 0, of: 5, next: 'tfsa-rrsp-fhsa', modules: [] }} onTab={noop}
                               onProjection={noop} onWhatIf={noop} />);
    expect(out).not.toContain('When your Anchor reaches 3 months');
    expect(out).toContain('gl-grow-cards two');
    expect(out).toContain('0 of 5 read');
    expect(out).toContain('Start with: TFSA, RRSP and FHSA · 4 min');
    expect(out).toContain('Start learning');
    expect(out).not.toMatch(/locked|unlock/i);
  });

  it('the words', () => {
    expect(calculatorWords()).toEqual({
      figure: '$13,970 – $17,310',
      line: '$100 a month for 10 years ($12,000 put in), at illustrative 3% to 7% a year.',
    });
    expect(learnWords(null).link).toBe('Start learning');
    expect(learnWords({ read: 5, of: 5, next: null, modules: [] }).line).toBe('You’ve read them all.');
    expect(projectionWords({ ...anchor, projection: { state: 'none', reason: 'no_pace' } }))
      .toMatchObject({ figure: 'No date yet', link: 'See why', to: 'projection' });
    expect(projectionWords({ ...anchor, projection: { state: 'full' } }))
      .toMatchObject({ figure: 'You’re there', to: 'anchor' });
  });
});
