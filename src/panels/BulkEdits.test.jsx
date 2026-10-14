import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { BulkEditsPanel, RangeSummary, SortRange, mostlyWords, stayingWords } from './BulkEdits.jsx';

const html = (el) => renderToStaticMarkup(el);
const text = (el) => html(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const primaries = (el) => (html(el).match(/pk-btn primary/g) ?? []).length;
const categories = [
  { name: 'Dining', group: 'lifestyle' }, { name: 'Travel', group: 'lifestyle' },
  { name: 'Groceries', group: 'essentials' }, { name: 'Income', group: 'income' },
];

describe('Sort a date range', () => {
  it('asks for a name, dates and one category, and says what happens', () => {
    const el = <SortRange categories={categories} onClose={() => {}} />;
    const t = text(el);
    for (const s of ['Sort a date range', 'Name', 'From', 'To', 'Sort everything as',
      'Every purchase between the dates gets the category you choose',
      'Pay and transfers stay as they are', 'Travel', 'Groceries', 'Sort them']) {
      expect(t).toContain(s);
    }
    expect(t).not.toContain('Income');                        // never a target
    expect(html(el)).toMatch(/disabled=""[^>]*>Sort them/);  // nothing to save yet
    expect(primaries(el)).toBe(1);
  });

  it('changing an edit starts from what it was', () => {
    const out = html(<SortRange categories={categories} onClose={() => {}}
                                edit={{ id: 3, name: 'Costa Rica', category: 'Travel',
                                        start_date: '2026-10-01', end_date: '2026-10-05' }} />);
    expect(out).toContain('value="Costa Rica"');
    expect(out).toContain('value="2026-10-01"');
    expect(out).toContain('Save changes');
  });

  it('the summary says what changes and what stays, with nothing to tick', () => {
    const p = { count: 6, total: 2472.79, category: 'Travel', staying_count: 2, in_dates: 8,
                categories: [{ category: 'Lodging' }, { category: 'Transport' },
                             { category: 'Dining' }, { category: 'Coffee' }],
                staying: { money_in: 2 } };
    const out = text(<RangeSummary preview={p} />);
    expect(out).toContain('6 purchases · $2,472.79 become Travel');
    expect(out).toContain('Mostly Lodging, Transport and Dining');
    expect(out).toContain('Staying as they are: 2 deposits.');
    expect(html(<RangeSummary preview={p} />)).not.toContain('checkbox');
    expect(mostlyWords([{ category: 'Dining' }])).toBe('Mostly Dining');
    expect(stayingWords({ other_edit: 1, transfer: 2 }))
      .toBe('2 transfers and card payments, 1 in another range you sorted');
    const none = text(<RangeSummary preview={{ count: 0, total: 0, category: 'Travel', categories: [],
                                               staying: {}, staying_count: 0, in_dates: 0 }} />);
    expect(none).toContain('No transactions between these dates');
    expect(none).not.toMatch(/\$0/);
  });

  it('the list has a way to sort a range', () => {
    expect(text(<BulkEditsPanel categories={categories} onClose={() => {}} />))
      .toContain('Sort a date range');
  });
});
