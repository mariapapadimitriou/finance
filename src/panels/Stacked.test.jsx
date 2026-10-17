import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import Stacked, { Progress, nameIn, steps } from './Stacked.jsx';

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};
const out = { key: 'u:a', kind: 'unsorted', to: 'M. Papas', learnable: true,
              txn: { id: 'a', date: '2026-10-07', merchant: 'e-Transfer to M. Papas', amount: 200,
                     account_name: 'TD Chequing ••4417' } };
const inn = { key: 'm:b', kind: 'money_in',
              txn: { id: 'b', date: '2026-10-01', merchant: 'e-Transfer from Sam Lee', amount: -300,
                     account_name: 'TD Chequing ••4417' } };

describe('Needs a look, stacked (R-07 to R-12)', () => {
  it('money out opens on "Was this spending?" with three answers, 0 of 3, and no Save yet (R-10)', () => {
    const page = html(<Stacked it={out} act={noop} sorted={noop} onSkip={noop} />);
    expect(page).toContain('e-Transfer to M. Papas');
    expect(page).toContain('Wednesday, October 7 · from TD Chequing ••4417');
    expect(page).toContain('-$200.00');
    expect(page).toContain('Was this spending?');
    for (const a of ['Yes, I bought something', 'No, I saved it', 'No, something else']) expect(page).toContain(a);
    expect(page).toContain('0 of 3');
    expect(page).toContain('Skip for now');
    expect(page).not.toContain('Save and next');
    expect(page).not.toContain('Why we ask');
  });

  it('money in opens on "Is this income?" in a soft panel, 0 of 2 (R-07)', () => {
    const page = html(<Stacked it={inn} act={noop} sorted={noop} onSkip={noop} />);
    expect(page).toContain('class="nl-tx in"');
    expect(page).toContain('+$300.00');
    expect(page).toContain('Is this income?');
    for (const a of ['Yes, it’s income', 'No, I moved my own money', 'No, something else']) expect(page).toContain(a);
    expect(page).toContain('0 of 2');
  });

  it('the paths: something else leads to what it was, then who to (R-11, R-12)', () => {
    const { start, S } = steps(out, null);
    expect(start).toBe('q1');
    const elseOpt = S.q1.options.find((o) => o.v === 'else');
    expect(elseOpt.to).toBe('what_out');
    expect(S.what_out.options.map((o) => o.label)).toEqual([
      'Moved between my own accounts', 'Lent to someone', 'Paying someone back',
      'A work expense, to be reimbursed', 'Not mine', 'Something else…']);
    expect(S.what_out.options.find((o) => o.v === 'lent').to).toBe('who_to');
    expect(S.who_to.title).toBe('Who to?');
  });

  it('a guessed category asks "Is this Dining out?" first', () => {
    const { S } = steps({ ...out, kind: 'category', guess: 'Dining' }, null);
    expect(S.q1.title).toMatch(/^Is this /);
    expect(S.q1.options.map((o) => o.v)).toEqual(['yes', 'other', 'else']);
  });

  it('a joint deposit goes from "something else" to "Who put this in?" (R-08)', () => {
    const { S } = steps({ ...inn, kind: 'joint_in' }, null);
    expect(S.q1.options.find((o) => o.v === 'else').to).toBe('who_in');
    expect(S.who_in.title).toBe('Who put this in?');
  });

  it('a nameless e-Transfer: something else → Paying me back → "Who sent this?" (R-09)', () => {
    const { S } = steps({ ...inn, kind: 'who_sent' }, { cases: [] });
    expect(S.q1.left).toBe(3);
    expect(S.what_in.options.find((o) => o.v === 'payback').to).toBe('name');
    expect(S.name.title).toBe('Who sent this?');
  });

  it('a payback offers the purchases it could be for, or money lent', () => {
    const cases = { cases: [{ key: 'payback', candidates: [{ id: 'c', merchant: 'Sushi Nami', date: '2026-10-08', amount: 85 }] }] };
    const { S } = steps(inn, cases);
    expect(S.what_in.options.find((o) => o.v === 'payback').to).toBe('pick_payback');
    expect(S.pick_payback.candidates).toHaveLength(1);
    expect(S.pick_payback.none).toBe('None of these: money I lent');
  });

  it('names come out of e-Transfer descriptions; the dots count what is done', () => {
    expect(nameIn('e-Transfer to M. Papas')).toBe('M. Papas');
    expect(nameIn('E-Transfer ***Q7k')).toBe('');
    expect(nameIn('Interac e-Transfer from Priya Shah')).toBe('Priya Shah');
    const dots = html(<Progress done={2} total={3} />);
    expect((dots.match(/nl-dot on/g) || []).length).toBe(2);
    expect(dots).toContain('2 of 3');
  });
});
