import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { InsightsPage } from './InsightsPanel.jsx';
import {
  CategoryView, MoneyView, ReviewMonth, SavingsView, SubscriptionsView, TrendView, WhereView,
} from './InsightsViews.jsx';
import {
  bandWords, compareText, donutArcs, groupRows, keptSentence, keptWords, savingsWords, stackedAreas,
  tileRows, topCategory, topRows, trendSentence, unsureWords, usualBar,
} from './insightsMath.js';

// Growth › Insights (THL-186 GR-24 to GR-27, THL-196 GR-28 to GR-32), as
// finance/growth_insights.py sends it on October 12: money in cents.

const MONTHS = ['2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10'];
const trendMonth = (month, essentials, lifestyle, extra = {}) => ({
  month, essentials, lifestyle, total: essentials + lifestyle, running: month === '2026-10', above: false, ...extra,
});
const cat = (category, group, amount, unsure = 0, share = 0) => ({ category, amount, unsure, share, group });
const where = (month) => ({
  month, total: 360000, unsure: 2,
  kinds: [
    { key: 'fixed', label: 'Fixed', total: 163400, categories: [
      cat('Rent', 'essentials', 145000, 0, 40), cat('Bills and phone', 'essentials', 18400, 0, 5)] },
    { key: 'variable', label: 'Variable', total: 196600, categories: [
      cat('Groceries', 'essentials', 42000, 0, 12), cat('Eating out', 'lifestyle', 39000, 0, 11),
      cat('Fun and going out', 'lifestyle', 31000, 0, 9), cat('Shopping', 'lifestyle', 28000, 2, 8),
      cat('Gifts', 'lifestyle', 21000, 0, 6), cat('Transit', 'essentials', 15600, 0, 4),
      cat('Books', 'lifestyle', 15000, 0, 4), cat('Pets', 'lifestyle', 5000, 0, 1)] },
  ],
  groups: [
    { key: 'essentials', label: 'Essentials', total: 221000, categories: [
      cat('Rent', 'essentials', 145000, 0, 40), cat('Groceries', 'essentials', 42000, 0, 12),
      cat('Bills and phone', 'essentials', 18400, 0, 5), cat('Transit', 'essentials', 15600, 0, 4)] },
    { key: 'lifestyle', label: 'Lifestyle', total: 139000, categories: [
      cat('Eating out', 'lifestyle', 39000, 0, 11), cat('Fun and going out', 'lifestyle', 31000, 0, 9),
      cat('Shopping', 'lifestyle', 28000, 2, 8), cat('Gifts', 'lifestyle', 21000, 0, 6),
      cat('Books', 'lifestyle', 15000, 0, 4), cat('Pets', 'lifestyle', 5000, 0, 1)] },
  ],
});
const history = (amounts, usual, running = true) => MONTHS.map((month, i) => ({
  month, amount: amounts[i], running: running && month === '2026-10', above: amounts[i] > usual,
}));

const october = {
  today: '2026-10-12', month: '2026-10', running: true, day: 12, days_in_month: 31, empty: false,
  months: MONTHS,
  tiles: { income: 420000, arrived: ['2026-10-01'], essentials: 124000, lifestyle: 52000, set_aside: 35000,
           fixed: 150000, variable: 26000 },
  accounts: [{ id: 'chq', name: 'Everyday' }, { id: 'card', name: 'Visa' }],
  filters: { account: null, span: 12, one_offs: 'in', show: null },
  usual: { months: ['2026-06', '2026-07', '2026-08'], curve: 'daily', left_out: ['2026-09'],
           unusual: ['2026-09'], month_unusual: false },
  vs_usual: [
    { key: 'essentials', label: 'Essentials', spent: 124000, usual: 215000, by_today: 120000 },
    { key: 'lifestyle', label: 'Lifestyle', spent: 52000, usual: 113000, by_today: 41000 },
  ],
  categories: [
    { category: 'Eating out', group: 'lifestyle', spent: 31000, usual: 30000, by_today: 23000,
      words: { kind: 'more', diff: 1000 }, unsure: 0,
      history: history([26000, 31000, 28000, 30000, 39000, 31000], 30000) },
    { category: 'Rent', group: 'essentials', spent: 145000, usual: 145000, by_today: 145000,
      words: { kind: 'same', diff: 0 }, unsure: 0,
      history: history([145000, 145000, 145000, 145000, 145000, 145000], 145000).map((h) => ({ ...h, above: false })) },
  ],
  trend: {
    months: [trendMonth('2026-05', 210000, 107000), trendMonth('2026-06', 212000, 116000),
             trendMonth('2026-07', 211000, 112000), trendMonth('2026-08', 214000, 119000),
             trendMonth('2026-09', 216000, 144000, { above: true }), trendMonth('2026-10', 124000, 52000)],
    band: { low: 320000, high: 335000, usual: 327000 },
    above: { essentials: [], lifestyle: ['2026-09'] },
  },
  where: where('2026-10'),
  where_last: where('2026-09'),
  money: MONTHS.map((month, i) => ({
    month, income: 420000, spent: [317000, 328000, 323000, 333000, 360000, 176000][i],
    set_aside: [35000, 40000, 35000, 50000, 25000, 35000][i],
    kept: month === '2026-10' ? null : [68000, 52000, 62000, 37000, 35000][i],
  })),
  income_went: { income: 420000, essentials: 215000, lifestyle: 113000, set_aside: 60000, left_over: 32000, short: 0 },
  savings: {
    total: 124000, change: 30000, since: '2026-09', first: '2026-05', anchor_started: true,
    parts: [{ key: 'anchor', label: 'Anchor', amount: 62000 }, { key: '1', label: 'Trip chest', amount: 32000 },
            { key: '2', label: 'New laptop', amount: 30000 }],
    series: MONTHS.map((month, i) => {
      const anchor = [10000, 20000, 30000, 40000, 50000, 62000][i];
      const trip = [10000, 20000, 30000, 15000, 25000, 32000][i];
      const laptop = [0, 5000, 10000, 15000, 20000, 30000][i];
      return { month, anchor, chests: { 1: trip, 2: laptop }, total: anchor + trip + laptop };
    }),
    events: [{ month: '2026-08', chest: '1', label: 'Trip chest opened' }],
  },
  subscriptions: {
    count: 2, monthly: 6549, yearly: 78588, reminders: [],
    rows: [{ merchant: 'Gym membership', monthly: 4900, yearly: 58800, choice: 'keep', remind: null },
           { merchant: 'Netflix', monthly: 1649, yearly: 19788, choice: 'review', remind: '2026-11' }],
  },
  recommendations: [],
};

const september = {
  ...october, month: '2026-09', running: false, day: 30, days_in_month: 30,
  tiles: { income: 420000, arrived: ['2026-09-01', '2026-09-15'], essentials: 215000, lifestyle: 113000, set_aside: 60000 },
  usual: { ...october.usual, months: ['2026-06', '2026-07', '2026-08'], left_out: [], month_unusual: false, unusual: [] },
  categories: [
    { category: 'Rent', group: 'essentials', spent: 145000, usual: 145000, words: { kind: 'same', diff: 0 }, history: [] },
    { category: 'Groceries', group: 'essentials', spent: 42000, usual: 38000, words: { kind: 'more', diff: 4000 }, history: [] },
    { category: 'Transit', group: 'essentials', spent: 15600, usual: 15600, words: { kind: 'same', diff: 0 }, history: [] },
    { category: 'Eating out', group: 'lifestyle', spent: 39000, usual: 30000, words: { kind: 'more', diff: 9000 }, history: [] },
    { category: 'Shopping', group: 'lifestyle', spent: 28000, usual: 34000, words: { kind: 'less', diff: 6000 }, history: [] },
    { category: 'Gifts', group: 'lifestyle', spent: 9000, usual: null, words: { kind: 'new', diff: null }, history: [] },
  ],
  where: where('2026-09'), where_last: null,
};

const empty = {
  ...october, empty: true, months: ['2026-10'],
  tiles: { income: 0, arrived: [], essentials: 0, lifestyle: 0, set_aside: 0 },
  usual: { months: [], curve: null, left_out: [], unusual: [], month_unusual: false },
  vs_usual: october.vs_usual.map((r) => ({ ...r, spent: 0, usual: null, by_today: null })),
  categories: [],
  trend: { months: [trendMonth('2026-10', 0, 0)], band: null, above: { essentials: [], lifestyle: [] } },
  where: { month: '2026-10', total: 0, unsure: 0, groups: [
    { key: 'essentials', label: 'Essentials', total: 0, categories: [] },
    { key: 'lifestyle', label: 'Lifestyle', total: 0, categories: [] }] },
  where_last: null,
  money: [{ month: '2026-10', income: 0, spent: 0, set_aside: 0, kept: null }],
  income_went: { income: 0, essentials: 0, lifestyle: 0, set_aside: 0, left_over: 0, short: 0 },
  savings: { total: 0, change: null, since: null, first: '2026-10', anchor_started: false, parts: [],
             series: [{ month: '2026-10', anchor: 0, chests: {}, total: 0 }], events: [] },
  subscriptions: { count: 0, monthly: 0, yearly: 0, rows: [], reminders: [] },
};

const nav = { show: () => {}, onTab: () => {}, toTransactions: () => {},
              onUnusual: () => Promise.resolve(), onChoice: () => Promise.resolve() };
const html = (el) => renderToStaticMarkup(el);
/** Calm: no red, no minus before $, never $0, NaN, undefined or null. */
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null|danger|exceed/i);
};
const tables = (out) => (out.match(/<table class="pk-sr"/g) || []).length;

describe('GR-28 the page', () => {
  const out = html(<InsightsPage d={october} show={() => {}} onTab={() => {}} />);

  it('has the header, the Growth pills with Learn, and the month switcher', () => {
    for (const text of ['Insights', 'Growth', 'October so far', 'Path', 'Projections', 'Budgets', 'Debts']) {
      expect(out).toContain(text);
    }
    expect(out).toMatch(/aria-current="page"[^>]*>Insights</);
    // Learn is built (THL-134): its pill opens it.
    expect(out).toMatch(/class="in-tab">Learn</);
    expect(out).not.toMatch(/disabled=""[^>]*>Learn</);
    expect(out).toContain('aria-label="Review September"');
  });

  it('shows the four tiles in her words', () => {
    for (const text of ['Income', '$4,200', 'Arrived Oct 1', 'Essentials', '$1,240', 'So far',
                        'Lifestyle', '$520', 'Set aside', '$350', 'Anchor and chests']) {
      expect(out).toContain(text);
    }
  });

  it('has the four chart cards, each with its figures as a table', () => {
    for (const text of ['Your spending, last 6 months', 'See the trend', 'Where October has gone so far', 'See all',
                        'Money in and out', 'See more', 'Your savings', '$1,240',
                        'In your Anchor and treasure chests. Up $300 since September.']) {
      expect(out).toContain(text);
    }
    expect(tables(out)).toBe(3);                     // trend, in and out, savings
    expect(out).toContain('Oct so far');
    expect(out).toContain('Everything else');
  });

  it('compares Essentials and Lifestyle with her usual, and sums up subscriptions', () => {
    expect(out).toContain('Compared with your usual');
    expect(out).toContain('$1,240 of a usual $2,150');
    expect(out).toContain('About where you usually are by October 12');
    expect(out).toContain('$110 more than usual by now');
    expect(out).toMatch(/viz-fill over/);            // champagne, never red
    expect(out).toContain('2 subscriptions · about $786 a year');
    expect(out).toContain('See them all');
    calm(out);
  });

  it('an empty ledger says so in words, with no empty charts', () => {
    const e = html(<InsightsPage d={empty} show={() => {}} onTab={() => {}} />);
    for (const text of ['None yet', 'Nothing has arrived yet', 'Nothing yet',
                        'No spending yet. Your months show here as they come in.',
                        'Nothing spent yet this month.', 'Nothing has come in or gone out yet.',
                        'Nothing in your Anchor or a treasure chest yet.',
                        'Your usual month appears once a full month is in.',
                        'No subscriptions spotted yet']) {
      expect(e).toContain(text);
    }
    expect(e).not.toContain('in-chart');
    expect(e).not.toContain('in-donut');
    expect(e).not.toContain('aria-label="Review');
    calm(e);
  });
});

describe('GR-25 review a past month', () => {
  const out = html(<ReviewMonth d={september} route={{ view: 'month', month: '2026-09' }} nav={nav} />);
  it('where the income went, categories in words, and leaving the month out', () => {
    for (const text of ['Your September', 'September 2026', 'Income $4,200', 'Where it went',
                        'Essentials $2,150', 'Lifestyle $1,130', 'Set aside $600', 'Left over $320',
                        'Same as usual', '$40 more than usual', '$60 less than usual',
                        'All 6 categories', 'Leave September out of my usual',
                        '0 months left out of your usual right now']) {
      expect(out).toContain(text);
    }
    expect(tables(out)).toBe(1);
    expect(out).toContain('aria-label="Back to this month"');
    calm(out);
  });
});

describe('GR-26 a category against usual', () => {
  const out = html(<CategoryView d={october} route={{ view: 'category', category: 'Eating out' }} nav={nav} />);
  it('says it in words, draws the usual as a dashed line, and offers the list and a budget', () => {
    for (const text of ['Lifestyle', 'Eating out', '$310 so far in October. By October 12 you usually spend $230.',
                        'Usual month: $300 (average of June, July and August; unusual months left out)',
                        'See the transactions', 'Set a budget for eating out']) {
      expect(out).toContain(text);
    }
    expect(out).toContain('in-usual-line');
    expect((out.match(/class="in-above"/g) || []).length).toBe(3);   // Jun, Sep and Oct so far
    expect(out).toContain('<th scope="row">September</th><td>$390</td><td>Above usual</td>');
    calm(out);
  });
});

describe('GR-27 subscriptions per year', () => {
  const out = html(<SubscriptionsView d={october} nav={nav} />);
  it('each by the year, the total, and a calm Keep or Review', () => {
    for (const text of ['Your subscriptions', '$786 a year', '2 subscriptions · about $65 a month',
                        'Gym membership', '$49.00 a month', '$588 a year', 'We’ll remind you in November',
                        'Pearl never cancels anything for you. Marking “Review” just reminds you next month.']) {
      expect(out).toContain(text);
    }
    expect(out).toMatch(/role="radio" aria-checked="true"[^>]*>Keep</);
    expect(html(<SubscriptionsView d={empty} nav={nav} />)).toContain('No subscriptions spotted yet.');
    calm(out);
  });
});

describe('GR-29 spending trend', () => {
  const out = html(<TrendView d={october} nav={nav} />);
  it('6 or 12 months, the band in words, and a way to review a month', () => {
    for (const text of ['Your spending trend', '6 months', '12 months',
                        'Essentials stayed close to your usual. Lifestyle went above your usual in September.',
                        '$3,600', 'Your usual month is $3,200 to $3,350. September is above it; nothing else stands out.',
                        'Review September', 'Mark a month as unusual']) {
      expect(out).toContain(text);
    }
    expect(tables(out)).toBe(1);
    calm(out);
  });
});

describe('GR-30 where the month went', () => {
  // A past month, asked for by name (this month is shown first otherwise).
  const out = html(<WhereView d={{ ...october, where: where('2026-09') }}
                              route={{ view: 'where', month: '2026-09' }} nav={nav} />);
  it('a ring, both groups, a dashed marker for what Pearl isn’t sure of, and the way to confirm', () => {
    for (const text of ['Where September went', 'Essentials · $2,210', 'Lifestyle · $1,390', 'Rent', '$1,450', '40%',
                        'Shopping', 'needs a look', 'Everything else', '$200',
                        'Shopping includes 2 purchases Pearl isn’t sure about. Confirm them and this updates.',
                        'Confirm 2 purchases', 'See all transactions', 'spent in September']) {
      expect(out).toContain(text);
    }
    expect(out).toContain('in-cat-dot in-guess');
    expect(out).toContain('Category suggested by Pearl, needs a look');
    calm(out);
  });
});

describe('GR-31 money in and out', () => {
  const out = html(<MoneyView d={october} nav={nav} />);
  it('paired bars, what she kept, and the month still going', () => {
    for (const text of ['Money in and out', 'You kept some of your income every month since May.',
                        'Money in', 'Spent', 'Set aside', 'What you kept', '$680', 'Oct so far',
                        'October is still going, so it shows once the month ends.']) {
      expect(out).toContain(text);
    }
    expect(tables(out)).toBe(1);
    calm(out);
  });
});

describe('GR-32 your savings', () => {
  const out = html(<SavingsView d={october} nav={nav} />);
  it('the total, each part, the chest opening labelled, and where next', () => {
    for (const text of ['Your savings', '$1,240', 'In your Anchor and treasure chests, since you joined in May.',
                        'Anchor', '$620', 'Trip chest', '$320', 'New laptop', '$300', 'Trip chest opened',
                        'Trip chest opened in August', 'Look ahead', 'Go to Goals']) {
      expect(out).toContain(text);
    }
    expect(tables(out)).toBe(1);
    calm(out);
  });
});

describe('the words and the geometry', () => {
  it('tiles never say $0', () => {
    const rows = tileRows(empty);
    expect(rows.map((r) => r.value)).toEqual(['None yet', 'Nothing yet', 'Nothing yet', 'Nothing yet']);
    expect(tileRows(september)[0].note).toBe('2 payments, latest Sep 15');
  });

  it('compares in words', () => {
    expect(compareText({ kind: 'same' })).toBe('Same as usual');
    expect(compareText({ kind: 'more', diff: 4000 })).toBe('$40 more than usual');
    expect(compareText({ kind: 'less', diff: 6000 })).toBe('$60 less than usual');
    expect(compareText({ kind: 'new' })).toBe('New this month');
  });

  it('the snapshot note for each pace', () => {
    const bar = usualBar(october.vs_usual[1], october);
    expect(bar.note('over')).toBe('$110 more than usual by now');
    expect(bar.note('under')).toBe('$110 less than usual by now');
    expect(bar.note('on')).toBe('About where you usually are by October 12');
    expect(usualBar({ ...october.vs_usual[1], spent: 120000 }, october).note('over-month'))
      .toBe('$70 over a usual month');
  });

  it('By category opens on the one furthest above usual', () => {
    expect(topCategory(october.categories)).toBe('Eating out');
    expect(topCategory([])).toBeNull();
  });

  it('trend, band, kept and savings sentences', () => {
    expect(trendSentence({ ...october.trend, above: { essentials: [], lifestyle: [] } }, 6))
      .toBe('Essentials stayed close to your usual. Lifestyle stayed close to your usual.');
    expect(bandWords({ ...october.trend, band: null }, 6)).toBe('Your usual month appears once a full month is in.');
    expect(keptSentence(empty.money)).toBe('What you kept shows here once a month ends.');
    expect(keptSentence([{ month: '2026-09', income: 1, spent: 2, kept: -100 }]))
      .toBe('Lately, everything that came in has gone out again.');
    expect(keptWords({ kept: -12000 })).toEqual({ value: 'Nothing', sr: '$120 more went out than came in', more: '$120' });
    expect(savingsWords({ ...october.savings, change: -12000 }))
      .toBe('In your Anchor and treasure chests. $120 used since September.');
    expect(savingsWords({ ...october.savings, anchor_started: false, change: null }))
      .toBe('In your treasure chests.');
  });

  it('lists: four a group and Everything else; three on the page', () => {
    const life = groupRows(october.where_last.groups[1]);
    expect(life.map((r) => r.name)).toEqual(['Eating out', 'Fun and going out', 'Shopping', 'Gifts', 'Everything else']);
    expect(life.at(-1)).toMatchObject({ amount: 20000, share: 5, other: true });
    // One left over keeps its own name.
    const five = groupRows({ ...october.where_last.groups[1],
                             categories: october.where_last.groups[1].categories.slice(0, 5) });
    expect(five.map((r) => r.name).at(-1)).toBe('Books');
    expect(topRows(october.where_last).map((r) => r.name)).toEqual(['Rent', 'Groceries', 'Eating out', 'Everything else']);
    expect(unsureWords(empty.where)).toBeNull();
  });

  it('a donut segment per value, none for nothing, and no ring at all for an empty month', () => {
    expect(donutArcs([1, 1, 0])).toHaveLength(3);
    expect(donutArcs([1, 1, 0])[2]).toBe('');
    expect(donutArcs([0, 0])).toEqual([]);
    expect(donutArcs([5])[0]).toMatch(/^M80,0A80,80/);
  });

  it('stacked areas sit on each other', () => {
    const [a, b] = stackedAreas([[10, 20], [5, 5]], 100, 100, 50);
    expect(a.top).toEqual([[0, 80], [100, 60]]);
    expect(b.top).toEqual([[0, 70], [100, 50]]);
    expect(stackedAreas([[0]], 100, 100, 0)).toEqual([]);
  });
});

describe('the Fixed / Variable lens and the filters (2026-10-14)', () => {
  it('the page has the lens switch and the four filters', () => {
    const out = html(<InsightsPage d={october} show={() => {}} onTab={() => {}} filters={{}} onFilter={() => {}} />);
    for (const s of ['By need', 'By kind', 'aria-label="Account"', 'aria-label="Months"', 'aria-label="Show"',
      'aria-label="One-offs"', 'Everyday', 'Fixed only', 'One-offs left out']) {
      expect(out).toContain(s);
    }
  });

  it('by kind, the tiles, the trend and where-it-went read Fixed and Variable', () => {
    const out = html(<InsightsPage d={october} show={() => {}} onTab={() => {}} lens="kind"
                                   filters={{}} onFilter={() => {}} />);
    expect(out).toContain('Fixed');
    expect(out).toContain('$1,500');                       // the fixed tile
    expect(out).toContain('Fixed and Variable each month');
    expect(out).toContain('in-fixed');                     // the kind lens's own colours
    expect(out).not.toContain('Essentials and Lifestyle each month');
  });

  it('by need is unchanged', () => {
    const out = html(<InsightsPage d={october} show={() => {}} onTab={() => {}} lens="need"
                                   filters={{}} onFilter={() => {}} />);
    expect(out).toContain('Essentials and Lifestyle each month');
    expect(out).not.toContain('Fixed and Variable each month');
  });
});
