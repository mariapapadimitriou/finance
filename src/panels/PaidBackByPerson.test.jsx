import { describe, expect, it } from 'vitest';
import { steps } from './SortCard.jsx';

// Money from a person (2026-10-28): Wealthsimple Pay or an e-Transfer with
// someone else's name asks whether they're paying her back first.
const cases = { cases: [{ key: 'payback', label: 'Someone paying me back', group: 'not_income', needs: 'candidates',
  candidates: [{ id: 'c', merchant: 'Sushi Nami', date: '2026-10-22', amount: 84 }] }] };
const inn = (extra) => ({ key: 'in:b', kind: 'money_in', from: 'Anastasia',
  txn: { id: 'b', date: '2026-10-24', merchant: 'Anastasia', amount: -42 }, ...extra });

describe('Is Anastasia paying you back?', () => {
  it('comes before Is this income?, with a likely purchase on top', () => {
    const { start, S } = steps(inn({ guess: { action: 'payback', charge: { id: 'c', merchant: 'Sushi Nami', date: '2026-10-22', amount: 84, likely: true } } }), cases);
    expect(start).toBe('person');
    expect(S.person.title).toBe('Is Anastasia paying you back?');
    expect(S.person.options.map((o) => o.label)).toEqual([
      'Yes, for Sushi Nami · Oct 22', 'Yes, for something else', 'No, it’s not a payback']);
    expect(S.person.options[1].to).toBe('pick_payback');
    expect(S.person.options[2].to).toBe('q1');
  });

  it('with no likely purchase, yes goes to which purchase', () => {
    const { start, S } = steps(inn({ guess: { action: 'person' } }), cases);
    expect(start).toBe('person');
    expect(S.person.options.map((o) => o.label)).toEqual(['Yes, they’re paying me back', 'No, it’s not a payback']);
  });

  it('money from nobody named still opens on Is this income?', () => {
    const { start } = steps(inn({ from: undefined, guess: { action: 'own' } }), cases);
    expect(start).toBe('q1');
  });

  it('a split waiting for her share is still asked first', () => {
    const { start } = steps(inn({ guess: { action: 'split', split: { name: 'Anastasia', charge_id: 'c', merchant: 'Sushi Nami', owes: 42 } } }), cases);
    expect(start).toBe('match');
  });
});
