import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarkTrip, TripsPanel } from './Trips.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('Trips (THL-174)', () => {
  it('Mark a trip asks for a name and dates and says what happens', () => {
    const out = html(<MarkTrip onClose={() => {}} />);
    for (const t of ['Mark a trip', 'Name', 'From', 'To', 'becomes Travel',
                     'Bills and pay stay as they are', 'Save trip']) {
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

  it('the trips list has a way to mark one', () => {
    expect(html(<TripsPanel onClose={() => {}} />)).toContain('Mark a trip');
  });
});
