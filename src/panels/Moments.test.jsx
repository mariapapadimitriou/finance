import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  BuildDone, MomentScreen, Placement, ProtectDone, buildDoneLine, placementRows, placementSub,
} from './Moments.jsx';

// THL-130 GR-06 Where you start, GR-07 Starting further along, GR-08 the
// basics done, GR-09 the Anchor at 3 months (GR-10 is in Projections.test.jsx).
// No phase names anywhere (THL-238).

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const NAMES = /Protect|Build|Unveil|Shine/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;

const protect = {
  phase: 'protect', invested: false, done: 2, of: 3, credit: null,
  rows: [{ key: 'income', done: true, amount: 4200, source: 'detected' },
         { key: 'bills', done: true, count: 6 },
         { key: 'essentials', done: false, month: null, known_by: '2026-11' }],
};

describe('GR-06 Where you start', () => {
  it('names where she starts and credits the steps already true', () => {
    const out = html(<Placement data={protect} onContinue={() => {}} />);
    for (const text of ['Here’s where you start', 'You start with the basics',
                        'We’ve looked at your accounts. Two of the three basic steps are already done.',
                        'Confirm your income', 'About $4,200 a month, found from your pay',
                        'Confirm your bills', '6 regular bills found',
                        'Sort your first month', 'After your first full month in Pearl',
                        'See my path']) {
      expect(out).toContain(text);
    }
    expect((out.match(/pj-check done/g) || []).length).toBe(2);
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
  });

  it('counts in words, and says so when nothing is done yet', () => {
    expect(placementSub({ ...protect, done: 1 }))
      .toBe('We’ve looked at your accounts. One of the three basic steps is already done.');
    expect(placementSub({ ...protect, done: 0 }))
      .toBe('We’ve looked at your accounts. Here are the three basic steps.');
    const rows = placementRows([{ key: 'income', done: true, amount: 3000, source: 'told' },
                                { key: 'bills', done: false, count: 0 }]);
    expect(rows[0].detail).toBe('About $3,000 a month, from what you told us');
    expect(rows[1].detail).toBe('None found yet');
  });
});

describe('GR-07 Starting further along', () => {
  it('past the basics: the Anchor, and what also counts', () => {
    const data = {
      phase: 'build', invested: false, done: 1, of: 3, credit: null,
      rows: [{ key: 'protect', done: true },
             { key: 'anchor', done: false, started: true, counted: 5470, target: 8700, usual: 2900, months: 1.9 },
             { key: 'saved_more', done: false, count: 1, of: 1, known_by: '2026-12', months: [] }],
    };
    const out = html(<Placement data={data} onContinue={() => {}} />);
    for (const text of ['You start at your Anchor', 'so the basics are already done', 'The basics',
                        'Income, bills and Essentials covered', 'Grow your Anchor to 3 months', '$5,470 · 1.9 of 3 months',
                        'Save more than you spend in 2 of 3 months', 'We’ll know by December']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
  });

  it('savings she already has give her Anchor a head start', () => {
    const data = {
      phase: 'build', invested: false, done: 1, of: 3,
      credit: { amount: 5470, target: 8700, accounts: ['sav'] },
      rows: [{ key: 'protect', done: true },
             { key: 'anchor', done: false, started: true, counted: 5470, target: 8700, usual: 2900, months: 1.9 },
             { key: 'saved_more', done: false, count: 1, of: 1, known_by: '2026-12', months: [] }],
    };
    const out = html(<Placement data={data} onContinue={() => {}} />);
    expect(out).toContain('You already have $5,470 in savings outside your chests, so your Anchor has a head start. Your income and bills are confirmed too.');
    expect(primaries(out)).toBe(1);
  });

  it('an Anchor already past three months starts at growing her money', () => {
    const data = {
      phase: 'unveil', invested: false, done: 2, of: 3, credit: null,
      rows: [{ key: 'protect', done: true }, { key: 'build', done: true, counted: 9100, target: 8700 },
             { key: 'invest', done: false }],
    };
    const out = html(<Placement data={data} onContinue={() => {}} />);
    for (const text of ['You start at growing your money',
                        'The basics are done, and your Anchor already covers 3 months of Essentials.',
                        'Your Anchor covers 3 months', '$9,100 · 3 months of Essentials',
                        'Open your first investment account', 'Whenever you’re ready. Guidance, not a gate.']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(NAMES);
  });
});

describe('GR-08 The basics done', () => {
  it('her money, assessed; the Anchor is the one primary', () => {
    const out = html(<ProtectDone target={8700} onAnchor={() => {}} onLater={() => {}} />);
    for (const text of ['The basics · Done', 'Here’s your money, assessed',
                        'Your income, bills and first month are sorted. Here’s your real picture.',
                        'Now open', 'Your Anchor',
                        'Next: set up your Anchor by picking your savings accounts. The milestone is 3 months of Essentials ($8,700).',
                        'Set up your Anchor', 'Not now']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(/confetti|points|streak/i);
    expect(out).not.toMatch(NAMES);
  });

  it('with the Anchor already set up, it opens it instead', () => {
    const out = html(<ProtectDone anchorStarted target={8700} />);
    expect(out).toContain('See your Anchor');
    expect(out).toContain('Next: grow your Anchor to 3 months of Essentials ($8,700)');
  });
});

describe('GR-09 The Anchor covers 3 months', () => {
  it('says so, and what comes next', () => {
    const out = html(<BuildDone anchor={{ target: 8700, counted: 8720 }} onUnveil={() => {}} onGoals={() => {}} />);
    for (const text of ['Your Anchor · Done', 'Your Anchor covers 3 months',
                        '$8,700 ready for big surprises, 3 months of Essentials. You’ve built your buffer. Growing your money is next.',
                        'See what’s next', 'Back to Save']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(NAMES);
  });

  it('never $0', () => {
    expect(buildDoneLine({ target: 0 })).toBe('You’ve built your buffer. Growing your money is next.');
  });
});

describe('the moment the app opens on', () => {
  const path = { phase: 'unveil', steps: [{ key: 'invest', done: true }],
                 phases: [{ key: 'protect', label: 'The basics', state: 'done' },
                          { key: 'build', label: 'Your Anchor', state: 'done' },
                          { key: 'unveil', label: 'Grow your money', state: 'now' }] };

  it('picks the screen for the milestone', () => {
    expect(html(<MomentScreen moment={{ phase: 'protect', anchor: { started: false }, path }} />))
      .toContain('Here’s your money, assessed');
    expect(html(<MomentScreen moment={{ phase: 'build', anchor: { target: 8700 }, path }} />))
      .toContain('Your Anchor covers 3 months');
    const unveil = html(<MomentScreen moment={{ phase: 'unveil', anchor: {}, path }} />);
    expect(unveil).toContain('You opened your first investment account');
    // A linked investment account counts, with no word from her.
    expect((unveil.match(/Done ✓/g) || []).length).toBe(3);
  });
});
