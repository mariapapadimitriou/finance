import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RecurringDetail, RecurringPage, longDay, scheduleWords } from './RecurringPanel.jsx';
import { hubRows } from './ProfilePanel.jsx';

const text = (el) => renderToStaticMarkup(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const rent = {
  id: 'rt:1', rule_id: 'recurring:rt:1', name: 'Transfer', account: 'Chequing', amount: 1500,
  cadence: 'monthly', when: 'every month, around the 1st', category: 'Rent & Housing', what: 'Rent',
  monthly: 1500, next: '2026-11-01', count: 3, last: '2026-10-01',
  transactions: [{ id: 'a', date: '2026-10-01', amount: 1500 }, { id: 'b', date: '2026-09-01', amount: 1500 }],
};
const savings = { ...rent, id: 'rt:2', rule_id: 'recurring:rt:2', name: 'TD Savings', amount: 200,
  cadence: 'biweekly', when: 'every two weeks, on Fridays', category: 'Saved', what: 'Into savings',
  monthly: 433.33, next: '2026-10-30' };

describe('Profile › Recurring transfers (2026-10-28)', () => {
  it('sums a month of them and lists each with its schedule and the next one', () => {
    const t = text(<RecurringPage data={{ transfers: [rent, savings], count: 2, asking: 0, monthly: 1933.33 }}
                                  onOpen={() => {}} />);
    for (const s of ['Recurring transfers', 'A month, on average', '$1,933.33', 'Rent',
      '$1,500.00 every month, around the 1st · from Chequing', 'Next Nov 1',
      'Into savings · TD Savings', '$200.00 every two weeks, on Fridays', 'Next Oct 30']) {
      expect(t).toContain(s);
    }
    expect(t).not.toContain('looks recurring');
  });

  it('says how many Needs a look is still asking about', () => {
    expect(text(<RecurringPage data={{ transfers: [rent], asking: 1, monthly: 1500 }} onOpen={() => {}} />))
      .toContain('1 more looks recurring.');
    expect(text(<RecurringPage data={{ transfers: [], asking: 2, monthly: 0 }} onOpen={() => {}} />))
      .toContain('2 more look recurring.');
  });

  it('with none yet, says where they come from', () => {
    const t = text(<RecurringPage data={{ transfers: [], asking: 0, monthly: 0 }} onOpen={() => {}} />);
    expect(t).toContain('No recurring transfers yet');
    expect(t).toContain('Needs a look asks whether it repeats');
  });

  it('one opens on what it is, the ones so far, and stopping it', () => {
    const t = text(<RecurringDetail item={rent} onClose={() => {}} onSave={() => {}} onStop={() => {}} />);
    for (const s of ['What is it?', 'Rent', 'Into savings', 'Moved to another of my accounts', 'Something else',
      'Next on Sunday, November 1.', 'The 3 so far', 'Thursday, October 1', '-$1,500.00',
      'Stop treating it as recurring']) {
      expect(t).toContain(s);
    }
  });

  it('is a row on Profile under Money', () => {
    const money = hubRows({ recurring: 2 }).find((g) => g.title === 'Money');
    const row = money.rows.find((r) => r.key === 'recurring');
    expect(row.name).toBe('Recurring transfers');
    expect(row.sub).toBe('2 recurring transfers');
    expect(scheduleWords({ amount: 50, when: 'every week, on Mondays', account: '' }))
      .toBe('$50.00 every week, on Mondays');
    expect(longDay('2026-10-28')).toBe('Wednesday, October 28');
  });
});
