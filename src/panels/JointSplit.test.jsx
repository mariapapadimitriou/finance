import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Whose } from './TransactionDetail.jsx';

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};
const base = { id: 'c', merchant: 'Costco', joint: 'Elena', full_amount: 80, inflow: false };

describe('Whose was it? on a joint account (2026-10-26)', () => {
  it('a charge split like every one from that name opens as Part of it, Always split ticked', () => {
    const page = html(<Whose tx={{ ...base, amount: 40, share_set: false, joint_split: 50 }} onBack={noop} onSave={noop} />);
    expect(page).toMatch(/aria-checked="true"[^>]*>Part of it/);
    expect(page).toContain('value="40"');
    expect(page).toMatch(/type="checkbox" checked=""\/>Always split Costco like this/);
  });

  it('one not split yet opens as Mine, with no Always split until Part of it', () => {
    const page = html(<Whose tx={{ ...base, amount: 80, share_set: false, joint_split: null }} onBack={noop} onSave={noop} />);
    expect(page).toMatch(/aria-checked="true"[^>]*>Mine/);
    expect(page).not.toContain('Always split');
    expect(page).toContain('Always all mine at Costco');
  });
});
