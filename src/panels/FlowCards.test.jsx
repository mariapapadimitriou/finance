import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import FlowCards, { barMath, cardWords, leftWords } from './FlowCards.jsx';
import { Avatar, CategoryChip, TxRow } from '../pearl/kit.jsx';
import { dayParts } from './TransactionsList.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('This month (Current design, 2026-10-20)', () => {
  it('one card: My income in lagoon, What I spent in rose, amounts on the right, nothing else', () => {
    const out = html(<FlowCards totals={{ spent: 3144.34, income: 2150 }} />);
    expect(out).toContain('aria-label="This month"');
    expect(out).toContain('My income');
    expect(out).toContain('What I spent');
    expect(out).toContain('tm-amt in">+$2,150.00');
    expect(out).toContain('tm-amt out">-$3,144.34');
    expect(out).toContain('class="tm-bar in"');
    expect(out).toContain('class="tm-bar out"');
    for (const gone of ['Outflows', 'Inflows', 'Net', 'Moving', 'Transfer', 'THIS MONTH', 'days left']) {
      expect(out).not.toContain(gone);
    }
  });

  it('spending past income is a hollow segment labelled "$x over", with the income line', () => {
    const out = html(<FlowCards totals={{ spent: 3144.34, income: 2150 }} />);
    expect(out).toContain('$994.34 over');
    expect(out).toContain('tm-income-line');
    const m = barMath(3144.34, 2150);
    expect(m.spent).toBe(1);
    expect(m.income).toBeCloseTo(2150 / 3144.34, 6);
    expect(m.over).toBeCloseTo(994.34, 2);
    expect(m.overFrac).toBeCloseTo(994.34 / 3144.34, 6);
  });

  it('with income ahead there is no overshoot and no line', () => {
    const out = html(<FlowCards totals={{ spent: 800, income: 2150 }} />);
    expect(out).not.toContain(' over');
    expect(out).not.toContain('tm-income-line');
    expect(barMath(800, 2150)).toEqual({ income: 1, spent: 800 / 2150, over: 0, overFrac: 0 });
    expect(barMath(0, 0)).toEqual({ income: 0, spent: 0, over: 0, overFrac: 0 });
  });

  it('a screen reader hears both figures and the difference', () => {
    expect(cardWords({ spent: 3144.34, income: 2150 })).toBe(
      'Income $2,150.00, spent $3,144.34. $994.34 more out than in.');
    expect(cardWords({ spent: 800, income: 2150 })).toBe(
      'Income $2,150.00, spent $800.00. $1,350.00 more in than out.');
  });

  it('days are named: Today, Yesterday, the weekday, then the date', () => {
    const now = new Date(2026, 9, 9);
    expect(dayParts('2026-10-09', now)).toEqual({ name: 'Today', date: 'Fri, Oct 9' });
    expect(dayParts('2026-10-08', now)).toEqual({ name: 'Yesterday', date: 'Thu, Oct 8' });
    expect(dayParts('2026-10-07', now)).toEqual({ name: 'Wednesday', date: 'Oct 7' });
    expect(dayParts('2026-10-02', now)).toEqual({ name: 'October 2', date: 'Friday' });
  });
});

describe('Transactions polish (2026-10-21)', () => {
  it('one quiet line under the bars says what is left, or how far spending ran past', () => {
    expect(leftWords(2000, 5121.24)).toBe('$3,121.24 left this month');
    expect(leftWords(3144.34, 2150)).toBe('$994.34 more out than in this month');
    expect(leftWords(10, 10)).toBe('');
    expect(html(<FlowCards totals={{ spent: 2000, income: 5121.24 }} />))
      .toContain('class="tm-left" aria-hidden="true">$3,121.24 left this month');
  });

  it('without a logo, the avatar is the category icon rather than initials', () => {
    expect(html(<Avatar name="Zyx Hardware" icon="home" />)).toContain('pk-avatar ic');
    expect(html(<Avatar name="Zyx Hardware" icon="home" />)).not.toContain('ZH');
    expect(html(<Avatar name="Zyx Hardware" logo="/l.png" icon="home" />)).toContain('<img');
    expect(html(<Avatar name="Zyx Hardware" />)).toContain('ZH');
  });

  it('a settled chip on a row is a button that changes the category; a guess still confirms', () => {
    const settled = html(<CategoryChip label="Dining" onChange={() => {}} />);
    expect(settled).toContain('pk-cat changeable');
    expect(settled).toContain('aria-label="Dining. Change category"');
    const guess = html(<CategoryChip label="Dining" suggested onConfirm={() => {}} onChange={() => {}} />);
    expect(guess).toContain('confirmable');
    expect(html(<CategoryChip label="Dining" />)).toContain('role="img"');
  });

  it('a row added by hand has a pen by its name', () => {
    const out = html(<TxRow name="Corner Bakery" manual amount={12.4}
                            chip={{ label: 'Dining', suggested: false }} />);
    expect(out).toContain('aria-label="Added by hand"');
    expect(out).toContain('pk-avatar ic');
  });
});
