import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PathPage } from './PathPanel.jsx';
import { KeepItGoing, StepPage, lapseLine, nextSentence, stepCopy } from './PathStep.jsx';

// THL-129 GR-02 Step not done yet, GR-03 Step done, GR-04 Keep it going, and
// the Path page (GR-01) opening each step.

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|null|\$0(?![.,\d])|\[object/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;

const base = {
  checked_on: '2026-10-01', next_check: '2026-11-01', current_phase: 'build',
  next: { text: 'Next: grow your Anchor to 3 months of Essentials, so a big surprise like a car repair doesn’t land on your credit card.',
          label: 'See your Anchor', action: 'goals' },
};

const full = {
  ...base, key: 'full', label: 'Grow your Anchor to 3 months', phase: 'build', phase_label: 'Your Anchor',
  also: false, index: 2, of: 2, state: 'now',
  facts: { started: true, target: 8700, counted: 5470, to_go: 3230, usual: 2900, months: 1.9, pace: 250,
           chests_monthly: 400, projection: { state: 'range', from: '2027-07', to: '2028-06' } },
};

const essentialsDone = {
  ...base, key: 'essentials', label: 'Cover your Essentials', phase: 'protect', phase_label: 'The basics',
  also: false, index: 3, of: 3, state: 'done',
  facts: { month: '2026-09', income: 4200, essentials: 2150, left: 2050 },
};

const lapsed = {
  ...essentialsDone, state: 'lapsed',
  facts: { month: '2026-10', income: 4200, essentials: 4480, left: -280,
           biggest: { merchant: 'Midas', category: 'Transport', amount: 1900 }, unusual: false },
};

describe('GR-02 Step not done yet', () => {
  it('says why, with her numbers, and what would help', () => {
    const out = html(<StepPage d={full} nav={{}} />);
    for (const text of ['Path', 'Your Anchor · Step 2 of 2', 'Grow your Anchor to 3 months', 'In progress',
                        'Why it’s not done yet',
                        'This is done when your Anchor, the cash savings you choose less what your chests hold, covers 3 months of your usual Essentials.',
                        '3 months of your usual Essentials', '$8,700', 'Your Anchor now', '$5,470',
                        'Still to go', '$3,230', 'How we worked this out', 'What would help',
                        'Your Anchor grows about $250 a month: what you put away, less the $400 your chests take. At this pace you’ll likely reach 3 months between July 2027 and June 2028.',
                        'See your Anchor']) {
      expect(out).toContain(text);
    }
    expect(out).not.toContain('Change the target');
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(/Protect|Build|Unveil|Shine/);
  });

  it('an Anchor not set up asks to set it up, never shows $0', () => {
    const d = { ...full, facts: { started: false, target: 8700, counted: 0, to_go: 8700, pace: 0 } };
    const out = html(<StepPage d={d} nav={{}} />);
    expect(out).toContain('Set up your Anchor');
    expect(out).not.toContain('Your Anchor now');
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
  });

  it('every step has words, whatever its state', () => {
    const cases = [
      { key: 'income', facts: { amount: 4340, source: 'detected', payer: 'Northwind', confirmed: false } },
      { key: 'income', facts: { amount: null, source: null } },
      { key: 'bills', facts: { count: 6, to_come: 363.48, confirmed: true } },
      { key: 'bills', facts: { count: 0, to_come: null, confirmed: false } },
      { key: 'essentials', facts: { month: null } },
      { key: 'essentials', facts: { month: '2026-09', income: 1500, essentials: 2000, left: -500 } },
      { key: 'setup', facts: { started: true, started_on: '2026-09-14', counted: 5470, accounts: 2 } },
      { key: 'setup', facts: { started: false, counted: 0, accounts: 0 } },
      { key: 'saved_more', facts: { months: [{ month: '2026-08', income: 4300, spent: 2300, saved: true },
                                            { month: '2026-09', income: 2100, spent: 2500, saved: false }],
                                    count: 1, of: 2, known_by: '2026-11' } },
      { key: 'cards', facts: { month: '2026-09', cards: [{ name: 'TD Visa ••4410', grew_by: 85 }] } },
      { key: 'cards', facts: { month: '2026-09', cards: [] } },
      { key: 'invest', facts: { report: null, linked: false } },
      { key: 'invest', facts: { report: { type: 'tfsa', label: 'TFSA' }, linked: false } },
    ];
    for (const c of cases) {
      for (const state of ['now', 'done']) {
        const d = { ...base, ...c, label: c.key, phase: 'build', phase_label: 'Your Anchor', also: false,
                    index: 1, of: 2, state };
        const out = html(<StepPage d={d} nav={{}} />);
        expect(out, `${c.key} ${state}`).not.toMatch(BAD);
        expect(primaries(out), `${c.key} ${state}`).toBeLessThanOrEqual(1);
        expect(stepCopy(d).why.text, `${c.key} ${state}`).toBeTruthy();
      }
    }
  });

  it('the essentials step that isn’t covered says by how much, calmly', () => {
    const d = { ...essentialsDone, state: 'now',
                facts: { month: '2026-09', income: 1500, essentials: 2000, left: -500 } };
    const c = stepCopy(d);
    expect(c.why.total).toEqual({ label: 'Short by', value: '$500' });
    expect(c.help.text).toBe('We check again on November 1. A month where what comes in covers your Essentials will do it.');
  });
});

describe('GR-03 Step done', () => {
  it('says why it’s done, and that earned steps stay earned', () => {
    const out = html(<StepPage d={essentialsDone} nav={{}} />);
    for (const text of ['The basics · Step 3 of 3', 'Your income covered your Essentials', 'Done',
                        'Why it’s done',
                        'In September, your income covered your Essentials with money left over.',
                        'Income', '$4,200', 'Essentials', '$2,150', 'Left over', '$2,050',
                        'How we worked this out',
                        'Checked on October 1. We check again each month, and earned steps stay earned, even after a rough month.']) {
      expect(out).toContain(text);
    }
    expect(out).not.toContain('What would help');
    expect(out).not.toMatch(BAD);
  });
});

describe('GR-04 Keep it going', () => {
  it('a bigger month, no red, nothing to fix', () => {
    const out = html(<KeepItGoing d={lapsed} nav={{}} />);
    for (const text of ['The basics · Step 3 of 3', 'Keep it going', 'Done', 'October was a bigger month',
                        'One charge of $1,900 at Midas pushed Essentials to $4,480, a little more than your income of $4,200. That happens.',
                        'The basics stay done. Nothing to fix; this is just so you know.',
                        'Mark October as unusual', 'See October in Insights', 'What happens next',
                        'We check again on November 1. Your next step stays the same: grow your Anchor to 3 months of Essentials.']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(/caution|error|\bred\b/);
    expect(out).not.toMatch(BAD);
  });

  it('StepPage shows GR-04 for a lapsed step', () => {
    expect(html(<StepPage d={lapsed} nav={{}} />)).toContain('October was a bigger month');
  });

  it('without one charge to point at, it says the total', () => {
    expect(lapseLine({ income: 4200, essentials: 6000, biggest: { merchant: 'Loblaws', amount: 210 } }))
      .toBe('Essentials came to $6,000, more than your income of $4,200. That happens.');
  });

  it('a month already marked unusual offers to put it back', () => {
    const out = html(<KeepItGoing d={{ ...lapsed, facts: { ...lapsed.facts, unusual: true } }} nav={{}} />);
    expect(out).toContain('October is marked unusual, so it’s left out of your usual month.');
    expect(out).toContain('Put it back');
  });

  it('the next step sentence', () => {
    expect(nextSentence({ ...base, next: { text: 'Every step on your path is done.' } })).toBe('');
  });
});

describe('the Path page opens each step (GR-01 → GR-02 to GR-04)', () => {
  const path = {
    phase: 'build', step: 2, of: 2, protect_done: true,
    lapse: { step: 'essentials', month: '2026-10', income: 4200, essentials: 4480 },
    phases: [{ key: 'protect', label: 'The basics', state: 'done' },
             { key: 'build', label: 'Your Anchor', state: 'now' },
             { key: 'unveil', label: 'Grow your money', state: 'ahead' }],
    steps: [{ key: 'setup', label: 'Set up your Anchor', done: true, started_on: '2026-09-14' },
            { key: 'full', label: 'Grow your Anchor to 3 months', done: false, target: 8700 }],
    also: [],
    next: base.next,
  };

  it('steps are buttons, the page is Wins, and a lapse says Keep it going', () => {
    const out = html(<PathPage path={path} onAction={() => {}} onStep={() => {}} onTab={() => {}} />);
    expect((out.match(/class="pt-step"/g) || []).length).toBe(2);
    expect(out).toContain('>Wins</h1>');
    expect(out).not.toContain('aria-label="Growth"');      // Wins is one page: no pills
    expect(out).toContain('Keep it going');
    expect(out).toContain('What happened in October');
    expect(primaries(out)).toBe(1);
  });
});
