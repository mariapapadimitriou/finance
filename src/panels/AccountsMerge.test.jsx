import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AccountDetail, MergeDialog, mergeCandidates } from './AccountsPanel.jsx';

const html = (el) => renderToStaticMarkup(el);
const base = { counted: true, joint: false, anchor: false, can_anchor: false, owing: true,
               status: 'up_to_date', balance: 400, transactions: 120, history_from: '2025-06-01' };
const feed = { ...base, id: 'new', name: 'Scotia Gold Amex', bank_name: 'Scotia Gold Amex',
               nickname: '', mask: '4876', institution: 'Scotiabank', kind: 'card', source: 'plaid' };
const statement = { ...base, id: 'old', name: 'Everyday Amex', bank_name: 'Gold Amex',
                    nickname: 'Everyday Amex', mask: '', institution: '', kind: 'card',
                    source: 'statement' };
const savings = { ...feed, id: 'sav', name: 'Tangerine', kind: 'savings' };
const cash = { ...feed, id: 'hand', name: 'Cash', source: 'hand', kind: 'card' };

describe('Same account as another one?', () => {
  it('offers only other accounts of the same kind with transactions', () => {
    expect(mergeCandidates(statement, [feed, statement, savings, cash]).map((o) => o.id))
      .toEqual(['new']);
  });

  it('is on a renamed account’s page', () => {
    const out = html(<AccountDetail a={statement} onMerge={() => {}} onSave={() => {}} />);
    expect(out).toContain('Same account as another one?');
  });

  it('says what merging does and which one stays', () => {
    const out = html(<MergeDialog a={statement} candidates={[feed]} onClose={() => {}}
                                  onMerge={() => Promise.resolve()} />);
    expect(out).toContain('Pearl can combine them so every purchase counts once');
    expect(out).toContain('Which one do you keep?');
    expect(out).toContain('Linked · up to date · 120 transactions');
    expect(out).toContain('Scotia Gold Amex ••4876 stays. Everyday Amex leaves Accounts and stops syncing.');
    expect(out).toMatch(/pk-btn primary[^>]*>Combine them/);
  });

  it('with nothing to merge with, says so', () => {
    const out = html(<MergeDialog a={statement} candidates={[]} onClose={() => {}}
                                  onMerge={() => Promise.resolve()} />);
    expect(out).toContain('There’s no other account of the same kind to combine with.');
    expect(out).toMatch(/disabled=""[^>]*>Combine them/);
  });
});
