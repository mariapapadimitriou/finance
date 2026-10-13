import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  BuildDone, MomentScreen, Placement, ProtectDone, buildDoneLine, placementRows, placementSub,
} from './Moments.jsx';

// THL-130 GR-06 Where you start, GR-07 Starting further along, GR-08 Protect
// done, GR-09 Build done (GR-10 is in Projections.test.jsx).

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;

const protect = {
  phase: 'protect', invested: false, done: 2, of: 3, credit: null,
  rows: [{ key: 'income', done: true, amount: 4200, source: 'detected' },
         { key: 'bills', done: true, count: 6 },
         { key: 'essentials', done: false, month: null, known_by: '2026-11' }],
};

describe('GR-06 Where you start', () => {
  it('names the phase and credits the steps already true', () => {
    const out = html(<Placement data={protect} onContinue={() => {}} />);
    for (const text of ['Here’s where you start', 'You start in Protect',
                        'We’ve looked at your accounts. Two of the three Protect steps are already done.',
                        'Confirm your income', 'About $4,200 a month, found from your pay',
                        'Confirm your bills', '6 regular bills found',
                        'Your income covers your Essentials', 'We’ll know after your first full month',
                        'See my path']) {
      expect(out).toContain(text);
    }
    expect((out.match(/pj-check done/g) || []).length).toBe(2);
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
  });

  it('counts in words, and says so when nothing is done yet', () => {
    expect(placementSub({ ...protect, done: 1 }))
      .toBe('We’ve looked at your accounts. One of the three Protect steps is already done.');
    expect(placementSub({ ...protect, done: 0 }))
      .toBe('We’ve looked at your accounts. Here are the three Protect steps.');
    const rows = placementRows([{ key: 'income', done: true, amount: 3000, source: 'told' },
                                { key: 'bills', done: false, count: 0 }]);
    expect(rows[0].detail).toBe('About $3,000 a month, from what you told us');
    expect(rows[1].detail).toBe('None found yet');
  });
});

describe('GR-07 Starting further along', () => {
  it('past Protect: Build, with the Anchor and what also counts', () => {
    const data = {
      phase: 'build', invested: false, done: 1, of: 3, credit: null,
      rows: [{ key: 'protect', done: true },
             { key: 'anchor', done: false, started: true, counted: 620, target: 2150 },
             { key: 'saved_more', done: false, count: 1, of: 1, known_by: '2026-12', months: [] }],
    };
    const out = html(<Placement data={data} onContinue={() => {}} />);
    for (const text of ['You start in Build', 'so Protect is already done', 'Protect',
                        'Income, bills and Essentials covered', 'Fill your Anchor', '$620 of $2,150',
                        'Save more than you spend in 2 of 3 months', 'We’ll know by December']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(BAD);
  });

  it('savings above a month of Essentials are counted as the Anchor', () => {
    const data = {
      phase: 'unveil', invested: false, done: 2, of: 3,
      credit: { amount: 2400, target: 2150, accounts: ['sav'] },
      rows: [{ key: 'protect', done: true }, { key: 'build', done: true, counted: 2400, target: 2150 },
             { key: 'invest', done: false }],
    };
    const out = html(<Placement data={data} onContinue={() => {}} />);
    for (const text of ['You start in Unveil',
                        'You already have $2,400 in savings, more than a month of Essentials. We’ve counted it as your Anchor.',
                        '$2,400 of $2,150', 'Open your first investment account',
                        'Whenever you’re ready. Guidance, not a gate.']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
  });
});

describe('GR-08 Protect done', () => {
  it('Ready to invest is open; the Anchor is the one primary', () => {
    const out = html(<ProtectDone onAnchor={() => {}} onReady={() => {}} onLater={() => {}} />);
    for (const text of ['Protect · Done', 'Protect is done',
                        'Your income covers your Essentials and your bills are known. That’s the base everything else sits on.',
                        'Now open', 'Ready to invest',
                        'A checklist to help you decide when you’re ready. Guidance, not a gate.',
                        'See the checklist', 'Start your Anchor', 'Not now']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(/confetti|points|streak/i);
  });

  it('with the Anchor already started, it opens it instead', () => {
    expect(html(<ProtectDone anchorStarted />)).toContain('See your Anchor');
  });
});

describe('GR-09 Build done', () => {
  it('the Anchor is full, and Unveil is next', () => {
    const out = html(<BuildDone anchor={{ target: 2150, counted: 2200, size: 1 }} onUnveil={() => {}} onGoals={() => {}} />);
    for (const text of ['Build · Done', 'Your Anchor is full',
                        '$2,150 set aside: one month of Essentials. You’ve built your buffer. Unveil is next.',
                        'See what Unveil means', 'Back to Goals']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
  });

  it('says what she chose, and never $0', () => {
    expect(buildDoneLine({ target: 6450, size: 3 }))
      .toBe('$6,450 set aside: three months of Essentials. You’ve built your buffer. Unveil is next.');
    expect(buildDoneLine({ target: 0 })).toBe('You’ve built your buffer. Unveil is next.');
  });
});

describe('the moment the app opens on', () => {
  const path = { phase: 'unveil', steps: [{ key: 'invest', done: true }],
                 phases: [{ key: 'protect', label: 'Protect', state: 'done' },
                          { key: 'build', label: 'Build', state: 'done' },
                          { key: 'unveil', label: 'Unveil', state: 'now' }] };

  it('picks the screen for the phase', () => {
    expect(html(<MomentScreen moment={{ phase: 'protect', anchor: { started: false }, path }} />))
      .toContain('Protect is done');
    expect(html(<MomentScreen moment={{ phase: 'build', anchor: { target: 2150, size: 1 }, path }} />))
      .toContain('Your Anchor is full');
    const unveil = html(<MomentScreen moment={{ phase: 'unveil', anchor: {}, path }} />);
    expect(unveil).toContain('You opened your first investment account');
    // A linked investment account counts, with no word from her.
    expect((unveil.match(/Done ✓/g) || []).length).toBe(3);
  });
});
