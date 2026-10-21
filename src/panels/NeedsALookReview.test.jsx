import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { SortedCard, minutes, questionLabel } from './NeedsALook.jsx';
import Stacked, { Done, Progress, steps } from './Stacked.jsx';

// Needs a look as the Current design page draws it (2026-10-20): To review,
// tapped answers, Undo in the card, Previous above it, the Sorted card with
// Next, and answers that reopen in place.

const html = (el) => renderToStaticMarkup(el);
const noop = () => {};
const out = { key: 'u:a', kind: 'unsorted', to: 'M. Papas', learnable: true,
              txn: { id: 'a', date: '2026-10-07', merchant: 'e-Transfer to M. Papas', amount: 200,
                     account_name: 'TD Chequing ••4417' } };
const inn = { key: 'm:b', kind: 'money_in',
              txn: { id: 'b', date: '2026-10-01', merchant: 'e-Transfer ***Q7k', amount: -2150,
                     account_name: 'TD Chequing ••4417' } };

describe('To review (TR-01)', () => {
  it('names the question each row will ask', () => {
    expect(questionLabel(out)).toBe('Where did this go?');
    expect(questionLabel({ kind: 'category', guess: 'Dining' })).toBe('Is this Dining?');
    expect(questionLabel({ kind: 'category', guess: 'Other' })).toBe('What was this?');
    expect(questionLabel(inn)).toBe('Is this income?');
    expect(questionLabel({ kind: 'money_in', guess: { action: 'split', split: {} } })).toBe('Paid back to you?');
    expect(questionLabel({ kind: 'joint_in' })).toBe('Who put this in?');
    expect(questionLabel({ kind: 'who_sent' })).toBe('Who sent this?');
    expect(questionLabel({ kind: 'income' })).toBe('What kind of income?');
    expect(questionLabel({ kind: 'duplicate' })).toBe('Same purchase?');
    expect(questionLabel({ kind: 'pay3' })).toBe('A third paycheque');
  });

  it('says how long the list takes', () => {
    expect(minutes(3)).toBe('about a minute');
    expect(minutes(8)).toBe('about 2 minutes');
  });
});

describe('One question at a time, tapped (R-10 to R-12)', () => {
  it('shows Undo in the card, the choices, Skip for now, and nothing to save', () => {
    const page = html(<Stacked it={out} act={noop} commit={noop} onSkip={noop} onBack={noop} />);
    expect(page).toContain('nl-pill nl-undo');
    expect(page).toContain('aria-label="Back to the list"');
    expect(page).toContain('Was this spending?');
    expect(page).toContain('Skip for now');
    expect(page).not.toContain('Save and next');
    expect(page).not.toContain('>Next<');
    expect(page).not.toContain('Change<');
  });

  it('answers so far are rows; Undo now takes back the last answer', () => {
    const page = html(<Stacked it={out} act={noop} commit={noop} onSkip={noop} onBack={noop}
                               initialPath={[{ step: 'q1', v: 'else' }, { step: 'what_out', v: 'lent' }]} />);
    expect(page).toContain('aria-label="Undo the last answer"');
    expect(page).toContain('aria-label="Change: Something else"');
    expect(page).toContain('aria-label="Change: Lent"');
    expect(page).toContain('Who to?');
    expect(page).toContain('2 of 3');
    expect(page).toContain('Press Enter, or pick a name');
  });

  it('a reopened answer expands in place, with the other answers still there', () => {
    const page = html(<Stacked it={out} act={noop} commit={noop} onSkip={noop} onBack={noop}
                               initialPath={[{ step: 'q1', v: 'else' }, { step: 'what_out', v: 'lent' }]}
                               initialEdit={0} />);
    // The first row shows its question and its options, the second stays folded.
    expect(page).toContain('nl-done-wrap open');
    expect(page).toContain('aria-label="Close: Was this spending?"');
    expect(page).toContain('aria-expanded="true"');
    expect(page).toContain('No, something else');
    expect(page).toContain('aria-label="Change: Lent"');
    expect(page).toContain('Who to?');
    const dots = html(<Done path={[{ step: 'q1', v: 'spent' }]} flow={steps(out, null)} editing={null} onOpen={noop} />);
    expect(dots).toContain('aria-expanded="false"');
    expect(dots).toContain('>Spending<');
  });

  it('"What kind of income?" lays its options out in two columns, with Pearl’s guess chosen', () => {
    const it_ = { ...inn, kind: 'income', guess: 'salary' };
    const page = html(<Stacked it={it_} act={noop} commit={noop} onSkip={noop} onBack={noop}
                               initialPath={[{ step: 'q1', v: 'income' }]} />);
    expect(page).toContain('What kind of income?');
    expect(page).toContain('pk-choices nl-grid');
    expect(page).toContain('pk-choice radio on');
  });
});

describe('The Sorted card (R-13)', () => {
  const entry = {
    key: 'u:a', it: out,
    answers: [{ step: 'q1', v: 'else', label: 'Something else' }, { step: 'what_out', v: 'lent', label: 'Lent' },
              { step: 'who_to', v: 'M. Papas', label: 'M. Papas' }],
    title: 'Lent to M. Papas.', detail: 'Not spending. Allowance goes up by $200.00 and M. Papas owes you $200.00.',
    undo: 'u1',
  };

  it('every dot filled with a check and Sorted, the answers as rows, the effect, and Next', () => {
    const page = html(<SortedCard entry={entry} onNext={noop} onUndo={noop} onReopen={noop} />);
    expect(page).toContain('aria-label="Sorted"');
    expect((page.match(/nl-dot on/g) || []).length).toBe(3);
    expect(page).toContain('nl-steps-sorted');
    expect(page).toContain('</svg> Sorted</span>');
    for (const a of ['Something else', 'Lent', 'M. Papas']) expect(page).toContain(`aria-label="Change: ${a}"`);
    expect(page).toContain('Not spending. Allowance goes up by $200.00');
    expect(page).toContain('nl-actions nl-next');
    expect(page).toContain('>Next <svg');
    expect(page).toContain('aria-label="Undo this change"');
    expect(page).not.toContain('Save');
  });

  it('looked at again from Previous, its button goes back to where she was', () => {
    const page = html(<SortedCard entry={entry} isPast onNext={noop} onUndo={noop} onReopen={noop} />);
    expect(page).toContain('Back to where I was');
  });

  it('the dots can say Sorted on their own', () => {
    expect(html(<Progress done={2} total={2} sorted />)).toContain('Sorted');
    expect(html(<Progress done={1} total={2} />)).toContain('1 of 2');
  });
});
