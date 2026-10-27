import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { DevicesSection } from './SecurityPanel.jsx';
import { ApprovalPrompt } from '../pearl/Session.jsx';

const html = (el) => renderToStaticMarkup(el);
const text = (el) => html(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

describe('Whose devices are asked (2026-10-26)', () => {
  it('the question names the account it is for', () => {
    const t = text(<ApprovalPrompt approval={{ id: 1, label: 'Chrome on Mac', near: 'Toronto, ON',
      account: { name: 'Maria', email: 'maria@example.com' } }} onAnswer={() => {}} onClose={() => {}} />);
    expect(t).toContain('Is this you signing in?');
    expect(t).toContain('To Maria’s account maria@example.com');
  });

  it('lists her devices, this one first, the others removable', () => {
    const t = text(<DevicesSection onRemove={() => {}} devices={[
      { id: 'a', label: 'Chrome on Mac', this: true, last_used_at: 1793068500 },
      { id: 'b', label: 'Safari on iPhone', this: false, last_used_at: 1793068500 }]} />);
    expect(t).toContain('Your devices');
    expect(t).toMatch(/Chrome on Mac This device Safari on iPhone Used .+ Remove/);
    expect(html(<DevicesSection onRemove={() => {}} devices={[{ id: 'a', label: 'Chrome on Mac', this: true }, { id: 'b', label: 'Safari on iPhone' }]} />).match(/pf-end-link/g)).toHaveLength(1);
  });
});
