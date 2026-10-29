import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { payWords } from './SortCard.jsx';
import { RulePanel, ruleWords } from './RulesPanel.jsx';

const text = (el) => renderToStaticMarkup(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

describe('Regular pay, remembered (2026-10-28)', () => {
  it('words the Remember box and the Sorted card for the payer', () => {
    const c = { key: 'regular_pay', remember: 'payer',
                remember_label: 'Always count deposits from Acme Corp as my regular pay' };
    expect(payWords(c, 'ACME CORP PAY')).toEqual({
      label: 'Always count deposits from Acme Corp as my regular pay',
      rule: 'Every deposit from Acme Corp counts as your regular pay from now on.',
      description: 'The ones already here and every new one count as income', on: true,
    });
    expect(payWords({ key: 'regular_pay', remember: null })).toBeNull();
    expect(payWords({ key: 'spending', remember: 'merchant' })).toBeNull();
  });

  it('shows on the Rules page as always your regular pay, and can only be removed', () => {
    const rule = { id: 'pay:payer:acme corp', kind: 'pay', name: 'Acme Corp', category: 'Income' };
    expect(ruleWords(rule)).toBe('Always your regular pay');
    const t = text(<RulePanel rule={rule} categories={[]} onClose={() => {}} onSave={() => {}} onDelete={() => {}} />);
    expect(t).toContain('Every deposit from Acme Corp counts as your regular pay');
    expect(t).toContain('Remove this rule');
    expect(t).not.toContain('Find a category');
  });
});
