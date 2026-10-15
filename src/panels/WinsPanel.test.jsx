import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ChallengesCard, RecapCard, StreakPanel, WinsPage, shareLines,
} from './WinsPanel.jsx';

// Wins (THL-239 W-01/W-03, THL-241 ST-01/02, THL-242 CH-01 to CH-05,
// THL-243 RC-01/02), as finance/wins.py sends it. No phase names, nothing
// in rose, nothing taken away.

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const NAMES = /Protect|Build|Unveil|Shine|Growth/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;
const noop = () => {};

const pearl = (key, label, earned, extra = {}) => ({ key, label, earned, on: earned ? '2026-10-02' : null,
  note: null, how: `How to earn ${label}`, path: true, ...extra });

const alex = {
  month: '2026-10', heading: '4 of 6 milestones on your path', first_month_away: false,
  done: 4, of: 6, earned: 6, total: 9,
  path: [{ key: 'assessed', label: 'Your money, assessed', state: 'earned', when: 'Sep 30' },
         { key: 'anchor_setup', label: 'Anchor set up', state: 'earned', when: 'Oct 2' },
         { key: 'anchor_quarter', label: 'Anchor a quarter there', state: 'earned', when: 'Oct 2' },
         { key: 'anchor_half', label: 'Anchor half there', state: 'earned', when: 'Oct 9' },
         { key: 'anchor_full', label: 'Anchor covers 3 months', state: 'next', when: 'Next · 63%' },
         { key: 'invest', label: 'Investing account opened', state: 'todo', when: 'Any time after' }],
  next: { key: 'anchor_full', title: 'Next: grow your Anchor to 3 months',
          line: '$5,470 of $8,700 · $3,230 to go · likely July 2027 to June 2028',
          label: 'See your Anchor', action: 'goals:anchor' },
  pearls: [pearl('assessed', 'Your money, assessed', true, { on: '2026-09-30' }),
           pearl('anchor_setup', 'Anchor set up', true),
           pearl('chest_opened', 'First treasure chest opened as planned', true, { on: '2026-10-06', note: 'Holiday gifts', path: false }),
           pearl('anchor_full', 'Anchor covers 3 months', false, { how: 'Your Anchor reaches 3 months of Essentials' }),
           pearl('invest', 'Investing account opened', false, { how: 'Open one wherever you like, then tell Pearl' })],
  streaks: [{ key: 'within', label: 'Months within safe to spend', unit: 'month', started: true, this: 1, best: 4,
              new_best: false, this_words: '1 month', best_words: 'Best 4', starts: '', rule: 'A month counts when your spending stayed within safe to spend.',
              note: 'August went over. A new run started in September, and your best run of 4 months is kept.',
              periods: [{ period: '2026-08', counted: false }, { period: '2026-09', counted: true }, { period: '2026-10', counted: null }] },
            { key: 'anchor', label: 'Months you added to your Anchor', unit: 'month', started: true, this: 5, best: 5,
              new_best: true, this_words: '5 months', best_words: 'Best 5 · new best', starts: '', rule: '',
              note: 'Every month since June, you’ve put something toward your Anchor.', periods: [] },
            { key: 'review', label: 'Weeks you cleared Needs a look', unit: 'week', started: true, this: 2, best: 6,
              new_best: false, this_words: '2 weeks', best_words: 'Best 6', starts: '', rule: '', note: null, periods: [] }],
  recap: { month: '2026-09', title: 'A good month for your Anchor',
           went_well: [{ key: 'within', text: 'You stayed within safe to spend.', share: 'Stayed within my plan' },
                       { key: 'put_away', text: 'You put away $650.', share: 'Kept building my Anchor', amount: 650 }],
           pearls: [{ key: 'anchor_half', label: 'Anchor half there', on: '2026-09-09' }], streaks: '', opportunity: null },
  next_recap: 'November',
  challenges: {
    ready: true,
    active: [{ id: 1, title: 'Coffee for a month', status: 'active', progress: { done: 38, target: 60, share: 0.633, over: false },
               words: { line: '$38 of $60. You’re on pace to spend less than September’s $86.', days: '16 days left', tone: 'brand' } }],
    suggested: [{ kind: 'no_spend_weekend', title: 'No-spend weekend', line: 'Your weekends average $140 of Lifestyle.' },
                { kind: 'cook_at_home', title: 'Cook-at-home week', line: 'Dining out ran 35% above usual.' },
                { kind: 'subscription_sweep', title: 'Subscription sweep', line: '7 subscriptions · about $1,427 a year.' }],
    past: [],
  },
  suggestion: { text: 'Your Anchor is half there. The growth calculator in Save is a good next read.', to: 'calculator', label: 'Open Save' },
};

describe('Wins (W-01)', () => {
  it('your path, pearls earned, streaks and the recap, challenges, and the Save pointer, in that order', () => {
    const out = html(<WinsPage data={alex} onAct={noop} onStep={noop} onSave={noop} onStreak={noop}
                               onChallenges={noop} onStart={noop} onChallenge={noop} onRecap={noop} />);
    const at = (s) => out.indexOf(s);
    expect(at('Your path')).toBeGreaterThan(0);
    expect(at('Pearls earned')).toBeGreaterThan(at('Your path'));
    expect(at('>Streaks<')).toBeGreaterThan(at('Pearls earned'));
    expect(at('September recap')).toBeGreaterThan(at('Pearls earned'));
    expect(at('>Challenges<')).toBeGreaterThan(at('>Streaks<'));
    for (const s of ['October 2026', '>Wins</h1>', '4 of 6 milestones on your path', 'Next · 63%', 'Any time after',
                     'Next: grow your Anchor to 3 months', '$5,470 of $8,700 · $3,230 to go · likely July 2027 to June 2028',
                     'See your Anchor', '6 of 9', 'Earned Sep 30', 'Earned Oct 6 · Holiday gifts',
                     'Your Anchor reaches 3 months of Essentials', 'Open one wherever you like, then tell Pearl',
                     'This run 1 month', 'Best 4', 'Best 5 · new best', 'This run 2 weeks', 'Best 6',
                     'A good month for your Anchor', 'See your recap',
                     'Coffee for a month', '16 days left', 'You’re on pace to spend less than September’s $86.',
                     'Suggested from your spending', 'No-spend weekend', 'Cook-at-home week', 'Subscription sweep',
                     'The growth calculator in Save is a good next read.', 'Open Save']) {
      expect(out).toContain(s);
    }
    expect((out.match(/wn-pearl earned/g) || []).length).toBeGreaterThanOrEqual(7);  // 4 on the path, 3 in the collection
    expect((out.match(/wn-pearl todo/g) || []).length).toBeGreaterThanOrEqual(3);    // dashed, never greyed-out failures
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
    expect(out).not.toMatch(/broke|failed|streak lost/i);
  });

  it('someone new (W-03): the first milestone is a month away, nothing is locked', () => {
    const fresh = {
      ...alex, heading: 'Your first milestone is a month away', first_month_away: true, done: 0, earned: 0,
      path: alex.path.map((p, i) => ({ ...p, state: i === 0 ? 'next' : 'todo', when: i === 0 ? 'After your first full month' : 'Comes later' })),
      next: { key: 'assessed', title: 'Next: your money, assessed',
              line: 'After your first full month in Pearl, you’ll see where your money goes: what you need, what you choose, and what’s left to build with.',
              label: 'Sort your first transactions', action: 'review' },
      pearls: alex.pearls.map((p) => ({ ...p, earned: false, on: null, note: null })),
      streaks: alex.streaks.map((s) => ({ ...s, started: false, starts: 'Starts after your first full month' })),
      recap: null, challenges: { ready: false, active: [], suggested: [], past: [] }, suggestion: null,
    };
    const out = html(<WinsPage data={fresh} onAct={noop} onStep={noop} />);
    for (const s of ['Your first milestone is a month away', 'After your first full month', 'Comes later',
                     'Sort your first transactions', '0 of 9', 'How to earn', 'Starts after your first full month',
                     'Your first recap comes in November', 'At the start of each month, Pearl sums up what went well.',
                     'Once Pearl knows your usual spending, it suggests short challenges from it. Always optional.']) {
      expect(out).toContain(s);
    }
    expect(out).not.toMatch(/locked|unlock/i);
    expect(out).not.toContain('Earned ');
    expect(out).not.toMatch(NAMES);
  });
});

describe('a streak (ST-01, ST-02)', () => {
  it('the missed-month state: this run beside the best, the months as pearls, and no rose', () => {
    const out = html(<StreakPanel streak={alex.streaks[0]} onClose={noop} />);
    for (const s of ['Months within safe to spend', 'This run', '1 month', 'Best run', '4 months',
                     'August went over. A new run started in September, and your best run of 4 months is kept.',
                     'wn-pearl todo sm', 'wn-pearl earned sm', 'wn-pearl unknown sm',
                     'A month counts when your spending stayed within safe to spend.']) {
      expect(out).toContain(s);
    }
    expect(out).not.toMatch(/broke|rose|caution/i);
  });

  it('a new best is a quiet note first', () => {
    const out = html(<StreakPanel streak={alex.streaks[1]} onClose={noop} />);
    expect(out.indexOf('New best: 5 months in a row')).toBeLessThan(out.indexOf('This run'));
    expect(out).toContain('Every month since June, you’ve put something toward your Anchor.');
  });
});

describe('challenges and the recap on the page', () => {
  it('over the target shows champagne, never rose', () => {
    const over = { ...alex.challenges, active: [{ ...alex.challenges.active[0],
      progress: { done: 70, target: 60, share: 1, over: true }, words: { ...alex.challenges.active[0].words, tone: 'champagne' } }] };
    const out = html(<ChallengesCard challenges={over} onAll={noop} onStart={noop} onOpen={noop} />);
    expect(out).toContain('wn-bar champagne');
    expect(out).not.toMatch(/rose|caution/);
  });

  it('the recap card leads with what went well', () => {
    const out = html(<RecapCard recap={alex.recap} nextRecap="November" onOpen={noop} />);
    expect(out).toContain('You stayed within safe to spend, you put away $650 and earned a pearl: Anchor half there.');
  });

  it('the share image shows wins as words; amounts only when asked', () => {
    expect(shareLines(alex.recap)).toEqual(['Stayed within my plan', 'Kept building my Anchor']);
    expect(shareLines(alex.recap, true)).toEqual(['Stayed within my plan', 'Kept building my Anchor · $650']);
  });
});
