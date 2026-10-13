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
  next: { text: 'Next: add to your Anchor.', label: 'Add to your Anchor', action: 'goals' },
};

const full = {
  ...base, key: 'full', label: 'Fill your Anchor', phase: 'build', phase_label: 'Build', also: false,
  index: 2, of: 2, state: 'now',
  facts: { started: true, target: 2150, counted: 620, to_go: 1530, size: 1, pace: 200,
           projection: { state: 'range', from: '2027-03', to: '2027-06' } },
};

const essentialsDone = {
  ...base, key: 'essentials', label: 'Cover your Essentials', phase: 'protect', phase_label: 'Protect',
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
    for (const text of ['Path', 'Build · Step 2 of 2', 'Fill your Anchor', 'In progress',
                        'Why it’s not done yet',
                        'Your Anchor is done when it holds one month of your usual Essentials.',
                        'Your usual month of Essentials', '$2,150', 'In your Anchor now', '$620',
                        'Still to go', '$1,530', 'How we worked this out', 'What would help',
                        'You’re adding about $200 a month. At this pace your Anchor is likely full between March and June 2027.',
                        'Add to your Anchor', 'Change the target']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
  });

  it('an Anchor not started asks to start it, never shows $0', () => {
    const d = { ...full, facts: { started: false, target: 2150, counted: 0, to_go: 2150, pace: 0 } };
    const out = html(<StepPage d={d} nav={{}} />);
    expect(out).toContain('Start your Anchor');
    expect(out).not.toContain('In your Anchor now');
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
      { key: 'first_stop', facts: { started: true, first_stop: 500, counted: 120, to_go: 380 } },
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
        const d = { ...base, ...c, label: c.key, phase: 'build', phase_label: 'Build', also: false,
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
    for (const text of ['Protect · Step 3 of 3', 'Your income covered your Essentials', 'Done',
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
    for (const text of ['Protect · Step 3 of 3', 'Keep it going', 'Done', 'October was a bigger month',
                        'One charge of $1,900 at Midas pushed Essentials to $4,480, a little more than your income of $4,200. That happens.',
                        'Protect stays done. Nothing to fix; this is just so you know.',
                        'Mark October as unusual', 'See October in Insights', 'What happens next',
                        'We check again on November 1. Your next step in Build stays the same: add to your Anchor.']) {
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
    phases: [{ key: 'protect', label: 'Protect', state: 'done' },
             { key: 'build', label: 'Build', state: 'now' },
             { key: 'unveil', label: 'Unveil', state: 'ahead' }],
    steps: [{ key: 'first_stop', label: 'Reach your Anchor’s first stop', done: true },
            { key: 'full', label: 'Fill your Anchor', done: false, target: 2150 }],
    also: [],
    next: base.next,
  };

  it('steps are buttons, the Growth pills are drawn, and a lapse says Keep it going', () => {
    const out = html(<PathPage path={path} onAction={() => {}} onStep={() => {}} onTab={() => {}} />);
    expect((out.match(/class="pt-step"/g) || []).length).toBe(2);
    expect(out).toContain('aria-label="Growth"');
    expect(out).toMatch(/aria-current="page"[^>]*>Path</);
    expect(out).toContain('Keep it going');
    expect(out).toContain('What happened in October');
    expect(primaries(out)).toBe(1);
  });
});
