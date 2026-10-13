import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { HomeBody } from './HomePanel.jsx';
import { ForYou, WhyPanel, dismissedWords } from './ForYou.jsx';

// What finance/recommendations.py sends (its tests use the same numbers).
const trend = {
  type: 'trend', label: 'Spending trend', impact: 612,
  title: 'Dining is running about 30% above usual',
  body: '$209 so far, compared with a usual $158 by October 9.',
  why: { title: 'Dining is above usual',
    text: 'So far this month you’ve spent $209 on dining. By October 9 you usually spend about $158 (average of July to September).',
    rule: 'We show this when a Lifestyle category is 25% or more above usual for this point in the month.',
    lines: [] },
  action: { label: 'See dining', to: 'transactions', filters: { month: '2026-10', category: 'Dining' } },
};
const subs = {
  type: 'subscriptions', label: 'Subscriptions', impact: 768,
  title: 'You pay $64 a month for 5 subscriptions',
  body: 'That’s $768 a year. Still using them all? Pearl won’t cancel anything.',
  why: { title: 'Your subscriptions, by the year', text: 'These charge you again and again.',
    rule: 'We show this when you have 2 or more subscriptions.',
    lines: [{ label: 'Netflix', monthly: 16.49, yearly: 197.88 }, { label: 'Spotify', monthly: 11.99, yearly: 143.88 }] },
  action: { label: 'Review subscriptions', to: 'transactions', filters: { recurring: '1', month: '2026-09' } },
};

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|NaN|undefined|null/);
  expect(text).not.toMatch(/should|must|warning|overspend/i);
};

describe('RC-01 For you', () => {
  it('each card: type, her numbers, why, a secondary action and Not for me', () => {
    const out = html(<ForYou cards={[subs, trend]} onAction={noop} onWhy={noop} onNotForMe={noop} />);
    expect(out).toContain('For you');
    expect(out).toContain('You pay $64 a month for 5 subscriptions');
    expect(out).toContain('$209 so far, compared with a usual $158 by October 9.');
    expect((out.match(/Why you’re seeing this/g) || []).length).toBe(2);
    expect((out.match(/Not for me/g) || []).length).toBe(2);
    expect(out).toMatch(/pk-btn secondary[^>]*>Review subscriptions/);
    expect(out).not.toMatch(/pk-btn primary/);                         // R1
    calm(out);
  });

  it('nothing to show, no section', () => {
    expect(html(<ForYou cards={[]} onAction={noop} onWhy={noop} onNotForMe={noop} />)).toBe('');
  });

  it('sits under the snapshot and keeps Home to one primary (L1, R1)', () => {
    const s = { month: '2026-10', state: 'ok', amount: 642.18, shown: 642.18, per_day: 27.92,
      days_left: 23, estimate: null, rows: [{ key: 'income', amount: 4300, lines: [] }] };
    const ds = { kind: 'normal', history_days: 120, asks_questions: false, answers: {} };
    const snap = { month: '2026-10', day: 9, days_in_month: 31, months_of_history: 3, rows: [] };
    const out = html(<HomeBody s={s} ds={ds} snap={snap} cards={[subs, trend]} reviewCount={2}
                               onSave={() => Promise.resolve()} onLink={noop} />);
    expect(out.indexOf('compared with a usual month')).toBeLessThan(out.indexOf('For you'));
    expect(out.indexOf('For you')).toBeLessThan(out.indexOf('need a look'));
    expect((out.match(/pk-btn primary/g) || []).length).toBe(0);
  });

  it('not while Pearl is learning', () => {
    const s = { month: '2026-10', state: 'ok', amount: 2605, shown: 2600, estimate: 'rough',
      income_source: 'told', per_day: 113, days_left: 23, rows: [{ key: 'income', amount: 4300, lines: [] }] };
    const ds = { kind: 'learning', history_days: 12, asks_questions: false, answers: {},
      learning_until: '2026-10-25', comparisons_from: '2026-11-01', spent_so_far: 300, bills_found: 2 };
    expect(html(<HomeBody s={s} ds={ds} cards={[subs]} onSave={() => Promise.resolve()} onLink={noop} />))
      .not.toContain('For you');
  });
});

describe('RC-03 why you’re seeing this', () => {
  it('the numbers, each subscription by the year, the rule, and secondary buttons', () => {
    const out = html(<WhyPanel card={subs} onClose={noop} onAction={noop} onNotForMe={noop} />);
    expect(out).toContain('Your subscriptions, by the year');
    expect(out).toContain('$16.49 a month · $198 a year');
    expect(out).toContain('We show this when you have 2 or more subscriptions.');
    expect(out).not.toMatch(/pk-btn primary/);                         // R1, the panel too
    expect((out.match(/pk-btn secondary/g) || []).length).toBe(2);
  });
});

describe('Not for me (THL-62)', () => {
  it('says what it hid and for how long', () => {
    expect(dismissedWords('trend')).toBe('Got it. We won’t show spending trend tips for 30 days.');
    expect(dismissedWords('subscriptions')).toBe('Got it. We won’t show subscription tips for 30 days.');
  });
});
