import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarkTrip, TripSummary, TripsPanel, mostlyWords, stayingWords } from './Trips.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('Trips (THL-174)', () => {
  it('Mark a trip asks for a name and dates and says what happens', () => {
    const out = html(<MarkTrip onClose={() => {}} />);
    for (const t of ['Mark a trip', 'Name', 'From', 'To', 'becomes Travel',
                     'Bills, pay and transfers stay as they are', 'Save trip']) {
      expect(out).toContain(t);
    }
    expect(out).toMatch(/disabled=""[^>]*>Save trip/);           // nothing to save yet
  });

  it('changing a trip starts from its name and dates', () => {
    const out = html(<MarkTrip trip={{ id: 3, name: 'Costa Rica', start_date: '2026-10-01',
                                       end_date: '2026-10-05' }} onClose={() => {}} />);
    expect(out).toContain('value="Costa Rica"');
    expect(out).toContain('value="2026-10-01"');
    expect(out).toContain('Save changes');
  });

  it('says what becomes Travel and what stays, with nothing to tick', () => {
    const p = { count: 4, total: 456.3, staying_count: 4,
                categories: [{ category: 'Lodging' }, { category: 'Transport' }, { category: 'Dining' },
                             { category: 'Coffee' }],
                staying: { bill: 2, transfer: 1, money_in: 1 } };
    const out = html(<TripSummary preview={p} />).replace(/<[^>]+>/g, ' ');
    expect(out).toContain('4 purchases · $456.30 becomes Travel');
    expect(out).toContain('Mostly Lodging, Transport and Dining');
    expect(out).toContain('Staying as they are: 2 bills and subscriptions, 1 transfer or card payment, 1 deposit.');
    expect(html(<TripSummary preview={p} />)).not.toContain('checkbox');
  });

  it('words', () => {
    expect(mostlyWords([{ category: 'Dining' }])).toBe('Mostly Dining');
    expect(mostlyWords([])).toBe('');
    expect(stayingWords({ yours: 1 })).toBe('1 you sorted yourself');
    const none = html(<TripSummary preview={{ count: 0, total: 0, categories: [], staying: {},
                                              staying_count: 0, in_dates: 0 }} />);
    expect(none).toContain('No transactions between these dates');
    expect(none).toContain('Profile › Accounts');
    const kept = html(<TripSummary preview={{ count: 0, total: 0, categories: [], staying: { bill: 2 },
                                              staying_count: 2, in_dates: 2 }} />);
    expect(kept).toContain('Nothing here looks like trip spending');
    expect(kept).toContain('Staying as they are: 2 bills and subscriptions.');
    expect(none).not.toMatch(/\$0/);
  });

  it('the trips list has a way to mark one', () => {
    expect(html(<TripsPanel onClose={() => {}} />)).toContain('Mark a trip');
  });
});
