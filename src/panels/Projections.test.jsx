import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Calculator, ProjectionsPage } from './ProjectionsPanel.jsx';
import { ForecastView, Next30View, SavingsView } from './ProjectionsViews.jsx';
import { ReadyPage, ReportPage, UnveilDone, checklistRows } from './Unveil.jsx';
import { PathPage } from './PathPanel.jsx';
import {
  anchorLine, calculator, comingUp, extraBounds, forecastLine, forecastSentence, futureValue,
  next30Line, parseAmount, parseYears, rangeWords, savingsAt, savingsWords,
} from './projectionsMath.js';

// Growth › Projections (THL-197 GR-33 to GR-37) and Unveil (THL-135 GR-16 to
// GR-18, THL-130 GR-10), as finance/projections_api.py sends them on October
// 13: money in cents, every projection a {low, high} range.

const html = (el) => renderToStaticMarkup(el);
const nav = { show: () => {}, onTab: () => {}, toGoals: () => {}, onChanged: () => {}, setData: () => {} };
const BAD = /NaN|undefined|null|\$0(?![.,\d])|−\$|-\$/;

const forecast = {
  month: '2026-10', day: 13, days_in_month: 31, spent: 176000, bills: 12700,
  bills_ahead: [{ date: '2026-10-18', label: 'Phone', amount: 6500, confirmed: true },
                { date: '2026-10-22', label: 'Gym', amount: 4500, confirmed: false }],
  rest: { low: 126300, high: 150300, basis: 'usual', months: ['2026-07', '2026-08', '2026-09'] },
  spend: { low: 315000, high: 339000 }, can_spend: 357000, left: { low: 18000, high: 42000 },
  line: Array.from({ length: 13 }, (_, i) => ({ day: i + 1, spent: 140000 + i * 3000 })),
  has_history: true, state: 'ok',
};

const series = Array.from({ length: 31 }, (_, i) => {
  const date = new Date(Date.UTC(2026, 9, 13 + i)).toISOString().slice(0, 10);
  const balance = i < 19 ? 160000 - i * 5000 : 400000 - i * 3000;
  return { date, balance, low: balance - 10000, high: balance + 10000 };
});
const next30 = {
  start: '2026-10-13', end: '2026-11-12', days: 30, balance: 160000, state: 'covered',
  per_day: { low: 2000, high: 4000, usual: 3000 },
  events: [
    { date: '2026-10-18', label: 'Phone', amount: 6500, kind: 'bill', confirmed: true },
    { date: '2026-11-01', label: 'Northwind', amount: 420000, kind: 'payday' },
    { date: '2026-11-01', label: 'Rent', amount: 145000, kind: 'bill', confirmed: true },
    { date: '2026-11-05', label: 'Car insurance', amount: 14200, kind: 'bill', confirmed: false },
  ],
  series,
  lowest: { date: '2026-10-31', amount: 106000, low: 96000, high: 116000, before_payday: true },
};

const savings = {
  month: '2026-10', by: '2027-10', now: 260000, extra: 0, state: 'ok',
  pace: { low: 20000, high: 25000, usual: 22000, months: ['2026-07', '2026-08', '2026-09'] },
  current: { low: 490000, high: 560000 }, what_if: null,
  history: [{ month: '2026-05', total: 150000 }, { month: '2026-08', total: 210000 },
            { month: '2026-10', total: 260000 }],
  opens: [{ month: '2027-03', label: 'New laptop chest opens' }],
};

const d = {
  today: '2026-10-13', empty: false, saving_goal: 0,
  anchor: { state: 'range', from: '2027-03', to: '2027-06', counted: 62000, target: 215000 },
  forecast, next30, savings,
};

describe('the words (projectionsMath)', () => {
  it('says every projection as a range, never a single figure', () => {
    expect(rangeWords({ low: 18000, high: 42000 })).toBe('$180 to $420');
    expect(rangeWords({ low: 30000, high: 30000 })).toBe('about $300');
    expect(rangeWords({ low: 0, high: 42000 })).toBe('up to $420');
    expect(forecastLine(forecast)).toBe('Likely $180 to $420 of safe-to-spend left on October 31.');
    expect(forecastSentence(forecast)).toBe('At your usual pace you’ll likely spend $3,150 to $3,390 this '
      + 'month. That leaves $180 to $420 of safe-to-spend.');
  });

  it('running over is said calmly, with no minus sign', () => {
    const over = { ...forecast, state: 'over', left: { low: -42000, high: -18000 } };
    expect(forecastLine(over)).toBe('At this pace, likely $180 to $420 more than you can spend by October 31.');
    expect(forecastSentence(over)).not.toMatch(BAD);
    const tight = { ...forecast, state: 'tight', left: { low: -5000, high: 12000 } };
    expect(forecastLine(tight)).toBe('Likely close to what you can spend by October 31: up to $120 left.');
    const noIncome = { ...forecast, state: 'no_income', left: null, can_spend: null };
    expect(forecastSentence(noIncome)).toContain('Add your income to see what that leaves.');
  });

  it('the Anchor line names the months, or says why there are none', () => {
    expect(anchorLine(d.anchor).text).toBe('Likely 3 months between March and June 2027');
    expect(anchorLine({ state: 'range', from: '2026-12', to: '2027-03' }).text)
      .toBe('Likely 3 months between December 2026 and March 2027');
    expect(anchorLine({ state: 'not_started' })).toMatchObject({ link: 'Set up your Anchor', view: 'start' });
    expect(anchorLine({ state: 'none' }).view).toBe('projection');
  });

  it('the next 30 days names the lowest point and the day before payday', () => {
    expect(next30Line(next30)).toBe('Lowest point about $1,060 on October 31, the day before payday.');
    expect(next30Line(next30, { long: true })).toBe('Your lowest point is likely about $1,060 on October 31, '
      + 'the day before payday. Everything coming up is covered.');
    expect(next30Line({ ...next30, state: 'short' })).toBe('It may run low around October 31, the day before payday.');
    expect(next30Line({ ...next30, state: 'no_balance', series: [], lowest: null }))
      .toContain('Profile › Accounts');
    const rows = comingUp(next30);
    expect(rows.map((r) => r.day)).toEqual(['Oct 18', 'Nov 1', 'Nov 1', 'Nov 5']);
    expect(rows.find((r) => r.kind === 'payday').name).toBe('Payday');
    expect(rows.find((r) => r.label === 'Car insurance').unconfirmed).toBe(true);
  });

  it('savings in a year, and the what-if, are the server’s arithmetic', () => {
    // 2,600 + 12 × 200 = 5,000; 2,600 + 12 × 250 = 5,600.
    expect(savingsAt(savings)).toEqual({ low: 500000, high: 560000 });
    expect(savingsAt(savings, 50)).toEqual({ low: 560000, high: 620000 });
    const w = savingsWords(savings, 50);
    expect(w.sentence).toBe('At your current pace, likely $5,000 to $5,600 by October 2027. Saving $50 more '
      + 'a month moves that to $5,600 to $6,200.');
    expect(savingsWords({ ...savings, state: 'no_history', pace: null }).figure).toBe('$2,600');
    expect(savingsWords({ ...savings, now: 0, state: 'no_history', pace: null }).figure).toBe('Not yet');
    expect(extraBounds(savings)).toEqual({ min: 0, max: 220, step: 10 });
    expect(extraBounds({ pace: null })).toEqual({ min: 0, max: 100, step: 10 });
  });
});

describe('the growth calculator (GR-17, GR-18)', () => {
  it('matches the handoff: $100 a month for 10 years', () => {
    expect([0.03, 0.05, 0.07].map((r) => futureValue(100, 10, r))).toEqual([13970, 15530, 17310]);
    expect([0.03, 0.05, 0.07].map((r) => futureValue(200, 20, r))).toEqual([65660, 82210, 104190]);
    const c = calculator(100, 10);
    expect(c.putIn).toBe(12000);
    expect(c.rows[2].putInShare + c.rows[2].growthShare).toBeCloseTo(1);
    expect(c.rows[0].label).toBe('At 3% a year');
  });

  it('reads what people type', () => {
    expect(parseAmount('$1,250')).toBe(1250);
    expect(parseAmount('lots')).toBeNull();
    expect(parseAmount('0')).toBeNull();
    expect(parseYears('10 years')).toBe(10);
    expect(parseYears('2.5')).toBeNull();
    expect(calculator(null, 10)).toBeNull();
  });

  it('is labelled illustrative, has a table, and no primary button', () => {
    const out = html(<Calculator onReady={() => {}} />);
    for (const text of ['Illustrative · not a prediction', 'What regular investing could grow to', 'Each month',
                        'For how long', 'You’d put in $12,000. At illustrative rates it could become:',
                        '$13,970', '$15,530', '$17,310', 'before fees and taxes',
                        'Learn how fees change this', '<table class="pk-sr">']) {
      expect(out).toContain(text);
    }
    // Ready to invest appears once she changes a figure (GR-18).
    expect(out).not.toContain('Ready to invest');
    expect(out).not.toContain('pk-btn primary');
    expect(html(<Calculator onReady={() => {}} initial={{ monthly: '200', years: '20' }} />)).toContain('$104,190');
  });
});

describe('GR-33 the page', () => {
  it('Anchor line, three look-ahead cards and the calculator, with the pills', () => {
    const out = html(<ProjectionsPage d={d} nav={nav} />);
    for (const text of ['What could happen', 'Projections', '> Save', 'Your Anchor',
                        'Likely 3 months between March and June 2027', 'See the projection', 'This month',
                        'See the forecast', 'Likely $180 to $420 of safe-to-spend left on October 31.',
                        'The next 30 days', 'See all', 'Lowest point about $1,060 on October 31',
                        'Your savings in a year', 'See more', '$5,000 to $5,600',
                        'Likely by October 2027, at your current pace.', 'What regular investing could grow to']) {
      expect(out).toContain(text);
    }
    expect((out.match(/<table class="pk-sr">/g) || []).length).toBe(4);
    expect(out).not.toContain('pk-btn primary');
    expect(out).not.toMatch(BAD);
  });

  it('GR-17 is the calculator on its own, a page of Save', () => {
    const out = html(<ProjectionsPage d={d} nav={nav} cards={false} />);
    expect(out).toContain('Growth calculator');
    expect(out).toContain('What regular investing could grow to');
    expect(out).not.toContain('The next 30 days');
    expect(out).not.toContain('class="in-tabs"');
  });

  it('an empty ledger says so in words, with no empty charts and no $0', () => {
    const empty = {
      ...d, empty: true, anchor: { state: 'not_started' },
      forecast: { ...forecast, state: 'none', spent: 0, bills: 0, bills_ahead: [], line: [], left: null,
                  can_spend: null, spend: { low: 0, high: 0 }, rest: { low: 0, high: 0, basis: 'this_month', months: [] } },
      next30: { ...next30, state: 'no_balance', balance: null, events: [], series: [], lowest: null },
      savings: { ...savings, now: 0, state: 'no_history', pace: null, history: [], opens: [] },
    };
    const out = html(<ProjectionsPage d={empty} nav={nav} />);
    expect(out).toContain('Nothing spent yet this month.');
    expect(out).toContain('Nothing coming up that we know of yet.');
    expect(out).toContain('Not set up yet');
    expect((out.match(/<table class="pk-sr">/g) || []).length).toBe(1);     // the calculator's
    expect(out).not.toMatch(BAD);
  });
});

describe('the detail views', () => {
  it('GR-34 where the month is heading', () => {
    const out = html(<ForecastView d={d} nav={nav} />);
    for (const text of ['Projections', 'Where October is heading', 'What you can spend this month: $3,570',
                        'Today · $1,760', '$3,390', '$3,150', 'Phone $65', 'Spent so far', 'Likely range',
                        'Bill still to come', 'How we worked this out']) {
      expect(out).toContain(text);
    }
    expect(out).toContain('Gym, due October 22, not confirmed yet');
    expect(out).not.toContain('See this week');                 // Home reads by the month only
    expect(out).not.toContain('pk-btn primary');
    expect(out).not.toMatch(BAD);
  });

  it('GR-35 the next 30 days, with unconfirmed bills dashed and a way to confirm them', () => {
    const out = html(<Next30View d={d} nav={nav} />);
    for (const text of ['The next 30 days', 'Lowest: about $1,060', 'Payday $4,200', 'Coming up',
                        'Car insurance', ' · not confirmed yet', 'Confirm', 'Expected balance',
                        'Oct 13', 'Nov 12', '$1,450']) {
      expect(out).toContain(text);
    }
    expect((out.match(/pj-bill unconfirmed/g) || []).length).toBe(1);
    expect((out.match(/pj-dot bill unconfirmed/g) || []).length).toBe(1);
    expect(out).not.toMatch(BAD);
  });

  it('GR-36 savings in a year: both wedges, the slider and one secondary action', () => {
    const out = html(<SavingsView d={d} nav={nav} />);
    for (const text of ['Your savings in a year', 'Saving $50 more a month moves that to $5,600 to $6,200.',
                        '$5,600 to $6,200', '$5,000 to $5,600', 'New laptop chest opens', 'Saved so far',
                        'Current pace', 'With $50 more', 'Save a bit more', '+$50 a month',
                        'A range, not a promise.', 'Use this pace for my Anchor', 'How we worked this out',
                        'type="range"']) {
      expect(out).toContain(text);
    }
    expect(out).not.toContain('pk-btn primary');
    expect(out).not.toMatch(BAD);
  });
});

const unveil = {
  checklist: [
    { key: 'protect', done: true },
    { key: 'anchor', done: false, started: true, counted: 62000, target: 215000 },
    { key: 'cards', done: true, months: 3, cards: 1, grew_in: null },
    { key: 'basics', done: false, available: true, read: 2, of: 5, next: 'index-funds-etfs' },
  ],
  partner: { configured: false, name: null, welcome: false, notify: false },
  report: null,
  path: { phases: [{ key: 'protect', label: 'The basics', state: 'done' },
                   { key: 'build', label: 'Your Anchor', state: 'done' },
                   { key: 'unveil', label: 'Grow your money', state: 'now' }] },
  types: [{ key: 'tfsa', label: 'TFSA' }, { key: 'rrsp', label: 'RRSP' }, { key: 'fhsa', label: 'FHSA' },
          { key: 'non_registered', label: 'Non-registered' }, { key: 'not_sure', label: 'Not sure' }],
};

describe('Unveil (GR-16, GR-37, GR-10)', () => {
  it('GR-16 the checklist is guidance; with no partner, GR-22 is its one primary', () => {
    const out = html(<ReadyPage data={unveil} nav={nav} />);
    for (const text of ['Path', 'Grow your money', 'Ready to invest', 'guidance, not a gate', 'Your checklist',
                        'The basics are done', 'Your income covers your Essentials', 'Your Anchor is under way',
                        '$620 of $2,150', 'See Anchor', 'No card balance growing', 'Checked over the last 3 months',
                        'Read the basics', '2 of 5 modules', 'Continue', 'Why both matter',
                        'Coming soon', 'We’re choosing a partner', 'registered in Canada',
                        'Tell me when Pearl partners with a provider', 'I opened an account elsewhere',
                        'Try the growth calculator']) {
      expect(out).toContain(text);
    }
    expect(out).not.toContain('Coming soon, with Learn');
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
    // No partner, so nothing is disclosed and nothing leaves Pearl.
    expect(out).not.toMatch(/may be paid|Continue to/i);
    expect(out).not.toMatch(BAD);
  });

  it('GR-16 once she has told Pearl', () => {
    const out = html(<ReadyPage data={{ ...unveil, report: { type: 'tfsa', label: 'TFSA', on: '2026-10-13' } }}
                                nav={nav} />);
    expect(out).toContain('You told Pearl you opened a TFSA, so that milestone is done.');
    expect(out).not.toContain('pk-btn primary');
  });

  it('a card balance that grew says when', () => {
    const rows = checklistRows([{ key: 'cards', done: false, months: 3, cards: 2, grew_in: '2026-09' }], nav);
    expect(rows[0].detail).toBe('A card balance grew in September');
  });

  it('GR-37 asks the kind of account only', () => {
    const out = html(<ReportPage data={unveil} onBack={() => {}} onDone={() => {}} />);
    for (const text of ['Ready to invest', 'Opened an investing account?', 'never ask for a login or a balance',
                        'What kind of account?', 'TFSA', 'RRSP', 'FHSA', 'Non-registered', 'Not sure',
                        'You can undo this in Profile.', 'Mark it done', 'Not yet']) {
      expect(out).toContain(text);
    }
    expect((out.match(/type="radio"/g) || []).length).toBe(5);
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
    expect(out).not.toMatch(/password|balance"|institution/i);
  });

  it('GR-10 Unveil done', () => {
    const out = html(<UnveilDone data={{ ...unveil, report: { type: 'tfsa', label: 'TFSA' } }} onPath={() => {}} />);
    for (const text of ['Grow your money · Done', 'You opened your first investment account',
                        'Every milestone on your path is done. What you’ve built stays yours.',
                        'The basics', 'Your Anchor', 'Done ✓', 'See your path']) {
      expect(out).toContain(text);
    }
    expect((out.match(/Done ✓/g) || []).length).toBe(3);
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
  });

  it('the Path opens Ready to invest and asks about Unveil', () => {
    const path = {
      phase: 'build', step: 2, of: 2, protect_done: true,
      phases: unveil.path.phases.map((p, i) => ({ ...p, state: ['done', 'now', 'ahead'][i] })),
      steps: [{ key: 'setup', label: 'Set up your Anchor', done: true },
              { key: 'full', label: 'Grow your Anchor to 3 months', done: false, target: 8700 }],
      also: [],
      next: { text: 'Next: grow your Anchor to 3 months of Essentials.', label: 'See your Anchor', action: 'goals' },
    };
    const out = html(<PathPage path={path} onAction={() => {}} onReady={() => {}} onUnveil={() => {}} />);
    expect(out).toContain('See the checklist');
    expect(out).toContain('Opened one? Tell Pearl');
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
  });
});
