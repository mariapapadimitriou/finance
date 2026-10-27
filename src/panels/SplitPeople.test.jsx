import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MAX_PEOPLE, SplitThis } from './Splits.jsx';

const html = (el) => renderToStaticMarkup(el);
const tx = (n) => ({ id: 'w', merchant: 'Wedding venue', full_amount: 5100,
  splitting: n ? { mode: 'even', watch: true,
                   people: Array.from({ length: n }, (_, k) => ({ name: `Guest ${k}`, amount: 100 })) } : null });

describe('Split this takes up to 50 people (2026-10-26: was 8)', () => {
  it('matches the server', () => { expect(MAX_PEOPLE).toBe(50); });
  it('still offers Add someone with nine, and with 49', () => {
    expect(html(<SplitThis tx={tx(9)} onSave={() => {}} />)).toContain('Add someone');
    expect(html(<SplitThis tx={tx(49)} onSave={() => {}} />)).toContain('Add someone');
  });
  it('stops at 50', () => {
    expect(html(<SplitThis tx={tx(50)} onSave={() => {}} />)).not.toContain('Add someone');
  });
});
