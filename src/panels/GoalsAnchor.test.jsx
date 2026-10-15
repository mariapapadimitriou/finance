import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  AnchorCard, AnchorDetail, StartAnchor, TargetExplained, anchorFigure, anchorSheet, countingWords,
  monthsWords, progressWords,
} from './GoalsAnchor.jsx';
import { ChestCard, ChestForm, firstFill } from './GoalsChests.jsx';

// THL-229 / THL-230: the Anchor is the cash savings she picks less what her
// chests hold; the milestone is three months of usual Essentials. Alex:
// $7,420 in savings, $1,950 in chests → $5,470, 1.9 months, 63%, $3,230 to
// go. No phase names anywhere (THL-238).

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const NAMES = /Protect|Build|Unveil|Shine/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;

const accounts = [
  { account_id: 'td', name: 'TD Savings', mask: '8820', kind: 'savings', balance: 1320, suggested: true, source: 'linked' },
  { account_id: 'tg', name: 'Tangerine Savings', mask: '0932', kind: 'savings', balance: 6100, suggested: true, source: 'linked' },
  { account_id: 'chq', name: 'TD Chequing', mask: '4417', kind: 'chequing', balance: 2340, suggested: false, source: 'linked' },
];
const alex = {
  started: true, started_on: '2026-09-14', earned: false, dipped: false, full: false,
  accounts: ['td', 'tg'], savings: 7420, chests: 1950, counted: 5470, usual: 2900, months: 1.9,
  target: 8700, to_go: 3230, share: 0.6287, saved_this_month: 200, chests_monthly: 400,
  counting: accounts.slice(0, 2), available_accounts: accounts,
  suggestion: { months: [{ month: '2026-07', essentials: 2840 }, { month: '2026-08', essentials: 2960 },
                         { month: '2026-09', essentials: 2900 }], average: 2900, amount: 2900, target: 8700 },
  projection: { state: 'range', from: '2027-07', to: '2028-06' },
  recent: [{ date: '2026-10-02', amount: 650, saved: true }, { date: '2026-09-03', amount: 560, saved: true }],
  pace: null, pace_months: [], unusual: [],
};
const goals = { month: '2026-10', phase: 'build', anchor: alex,
                chests: [{ id: 1, name: 'Japan trip', held: 750 }, { id: 2, name: 'New laptop', held: 600 },
                         { id: 3, name: 'Holiday gifts', held: 600 }] };

describe('the words', () => {
  it('Alex’s numbers (THL-230 acceptance)', () => {
    expect(anchorFigure(alex)).toBe('$5,470 · 1.9 months of Essentials');
    expect(progressWords(alex)).toBe('63% of the way to 3 months · likely Jul 2027 – Jun 2028');
    expect(countingWords(7420, 1950)).toBe('$7,420 in savings − $1,950 in treasure chests = $5,470 Anchor');
    expect(countingWords(7420, 0)).toBe('$7,420 in savings = $7,420 Anchor');
    expect(monthsWords(3)).toBe('3 months');
    expect(monthsWords(1)).toBe('1 month');
    expect(monthsWords(2.64)).toBe('2.6 months');
  });

  it('X-03: the sheet adds the savings, takes out the chests, divides by a usual month', () => {
    const sheet = anchorSheet(goals);
    expect(sheet.title).toBe('Your Anchor: $5,470');
    expect(sheet.sub).toBe('The cash savings you have, less what your chests hold.');
    expect(sheet.rows.map((r) => [r.label, r.display])).toEqual([
      ['In your savings', '$7,420'],
      ['In treasure chests', '− $1,950'],
      ['Your Anchor', '$5,470'],
      ['Your usual Essentials', '÷ $2,900'],
    ]);
    expect(sheet.rows[0].lines.map((l) => l.label)).toEqual(['TD Savings ••8820', 'Tangerine Savings ••0932']);
    expect(sheet.rows[1].lines.map((l) => l.label)).toEqual(['Japan trip', 'New laptop', 'Holiday gifts']);
    expect(sheet.rows[3].detail).toBe('A month, over the last 3 months');
    expect(sheet.total).toEqual({ label: 'Months it covers', detail: 'The milestone is 3 months', display: '1.9 months' });
  });
});

describe('the Anchor on Save (G-01, G-02, A-01, A-05, A-06)', () => {
  it('while it grows: step 2 of 2, the figure, and how far to 3 months', () => {
    const out = html(<AnchorCard goals={goals} onStart={() => {}} onOpen={() => {}} onTab={() => {}} />);
    for (const s of ['Step 2 of 2', 'Your Anchor', 'See details', '$5,470 · 1.9 months of Essentials',
                     '63% of the way to 3 months · likely Jul 2027 – Jun 2028', 'viz-fill nacre']) {
      expect(out).toContain(s);
    }
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
  });

  it('not set up yet, and before the basics are done', () => {
    const fresh = { ...goals, anchor: { ...alex, started: false, counted: 0, months: null, share: 0 } };
    const out = html(<AnchorCard goals={fresh} onStart={() => {}} onOpen={() => {}} onTab={() => {}} />);
    expect(out).toContain('Step 1 of 2');
    expect(out).toContain('It’s the cash savings you already have, less what your treasure chests hold.');
    expect(out).toMatch(/pk-btn primary[^>]*>Set up your Anchor/);
    const early = html(<AnchorCard goals={{ ...fresh, phase: 'protect' }} onStart={() => {}} onOpen={() => {}} onTab={() => {}} />);
    expect(early).toContain('Comes next');
    expect(early).toContain('It becomes your focus once the basics are covered, and you can set it up any time.');
    expect(early).toContain('Set it up early');
    expect(primaries(early)).toBe(0);
    expect(early).not.toMatch(NAMES);
  });

  it('three months reached, and after a dip', () => {
    const full = { ...goals, anchor: { ...alex, counted: 8700, months: 3, share: 1, to_go: 0, full: true, earned: true, projection: { state: 'full' } } };
    const out = html(<AnchorCard goals={full} onStart={() => {}} onOpen={() => {}} onTab={() => {}} />);
    for (const s of ['Milestone reached', 'Your Anchor covers 3 months', '$8,700 · 3 months of Essentials',
                     'Three months of Essentials, ready for a big surprise. If your Anchor dips below 3 months, Pearl lets you know.',
                     'See what’s next on Wins']) {
      expect(out).toContain(s);
    }
    const dip = { ...goals, anchor: { ...alex, counted: 7650, months: 2.6, share: 0.879, to_go: 1050, full: false, earned: true, dipped: true } };
    const d = html(<AnchorCard goals={dip} onStart={() => {}} onOpen={() => {}} onTab={() => {}} />);
    for (const s of ['Keep it going', '$7,650 · 2.6 months of Essentials', 'Just under 3 months · put a little away when you can',
                     'A big surprise dipped into it, which is what it’s for. The milestone stays reached.', 'Top it up when you can']) {
      expect(d).toContain(s);
    }
    expect(d).not.toMatch(NAMES);
  });

  it('A-04: the detail page', () => {
    const out = html(<AnchorDetail goals={goals} onBack={() => {}} onProjection={() => {}} onAccounts={() => {}} onExplain={() => {}} />);
    for (const s of ['Save', 'Your Anchor', '$5,470 · 1.9 months of Essentials', 'How we worked this out',
                     '3 months of Essentials', '$3,230 to go', 'When you’ll reach 3 months',
                     'Likely between July 2027 and June 2028', 'See the range', 'Your savings', 'TD Savings ••8820',
                     '$1,320', 'Tangerine Savings ••0932', '$6,100', 'In treasure chests', '− $1,950', 'Change accounts',
                     'Recent', 'Oct 2 · Put away', '$650']) {
      expect(out).toContain(s);
    }
    expect(out).not.toMatch(BAD);
    expect(out).not.toMatch(NAMES);
  });
});

describe('setting it up (A-01, A-02) and the sheet (X-03)', () => {
  it('A-01: the milestone, a benchmark she can’t change, then the accounts', () => {
    const fresh = { ...goals, anchor: { ...alex, started: false, accounts: [] } };
    const out = html(<StartAnchor goals={fresh} onClose={() => {}} onDone={() => {}} onSeeAnchor={() => {}} />);
    for (const s of ['Step 1 of 2', 'Set up your Anchor', 'Your milestone', '$8,700',
                     'Three months of your usual Essentials ($2,900 a month). A benchmark, not a goal you set.',
                     'How we worked this out', 'Next, pick the savings accounts that make up your Anchor.', 'Continue']) {
      expect(out).toContain(s);
    }
    expect(out).not.toContain('How much cushion');
    expect(out).not.toMatch(/<input/);
    expect(out).not.toMatch(NAMES);
  });

  it('X-03 as a sheet, with the way to the what-if', () => {
    const out = html(<TargetExplained goals={goals} onClose={() => {}} onWhatIf={() => {}} />);
    expect(out).toContain('Your Anchor: $5,470');
    expect(out).toContain('Months it covers');
    expect(out).toContain('1.9 months');
    expect(out).toContain('Want to reach 3 months sooner? Try putting away a bit more');
    expect(out).toMatch(/pk-btn primary[^>]*>Got it/);
  });
});

describe('chests fill from the Anchor (G-03)', () => {
  it('the form says what comes out of the Anchor on the 1st, and that safe to spend doesn’t change', () => {
    const out = html(<ChestForm goals={{ ...goals, spend_categories: ['Travel'], bank_funded: [] }}
                                onClose={() => {}} onSaved={() => {}} onStartAnchor={() => {}} />);
    for (const s of ['Start a chest', 'Name', 'How much?', 'By a date', 'Every year', 'Start chest']) {
      expect(out).toContain(s);
    }
    expect(out).not.toContain('Set aside from your safe-to-spend');
    expect(out).not.toMatch(NAMES);
    expect(firstFill(new Date(2026, 9, 15))).toBe('2026-11-01');
    expect(firstFill(new Date(2026, 9, 1))).toBe('2026-10-01');
    expect(firstFill(new Date(2026, 11, 20))).toBe('2027-01-01');
  });

  it('a chest that hasn’t had its first 1st yet never says $0', () => {
    const chest = { id: 1, name: 'Japan trip', held: 0, target: 3000, monthly: 272.73, share: 0, ready: false,
                    cadence: 'once', target_date: '2027-09-01', ready_by: '2027-09', catching_up: false };
    const out = html(<ChestCard chest={chest} onOpen={() => {}} onTreasure={() => {}} />);
    expect(out).toContain('Nothing yet');
    expect(out).toContain('$272.73 a month');
    expect(out).not.toMatch(BAD);
  });
});
