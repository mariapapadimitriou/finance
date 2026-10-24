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
    for (const a of ['Yes, I spent something', 'No, I saved it', 'No, something else']) expect(page).toContain(a);
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
    // Tiles (2026-10-23): one idea two ways is one tile that asks which.
    expect(S.what_out.tiles).toBe(true);
    expect(S.what_out.options.map((o) => o.label)).toEqual([
      'A bill', 'Split with others', 'My own money', 'A loan', 'Not mine']);
    expect(S.what_out.options.find((o) => o.v === 'g:loan').to).toBe('what_out_loan');
    expect(S.what_out_loan.options.map((o) => o.label)).toEqual(['I lent it to someone', 'I’m paying back a loan']);
    expect(S.what_out_loan.options.find((o) => o.v === 'lent').to).toBe('who_to');
    expect(S.what_out_not.options.map((o) => o.v)).toEqual(['work', 'not_mine']);
    // "My own money" holds only Moved here (Saved was the first question), so it goes straight there.
    expect(S.what_out.options.find((o) => o.label === 'My own money').v).toBe('moved');
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

describe('an e-Transfer whose message names a purchase (2026-10-21)', () => {
  const said = { id: 'u', merchant: 'Uber Eats', date: '2026-10-14', amount: 54.6, paid_back: 18.2, memo: true };
  const inn = { key: 'in:d', kind: 'money_in', guess: { action: 'memo', charge: said, memo: 'uber eats' },
    txn: { id: 'd', date: '2026-10-16', merchant: 'e-Transfer from Denise Rao', amount: -18.2, memo: 'uber eats' } };

  it('asks about that purchase first, with the message', () => {
    const { start, S } = steps(inn, { cases: [], memo: 'uber eats', memo_match: said });
    expect(start).toBe('memo');
    expect(S.memo.title).toBe('Is Denise Rao paying you back for Uber Eats?');
    expect(S.memo.sub).toBe('Their message says “uber eats”.');
    expect(S.memo.options.map((o) => o.v)).toEqual(['yes', 'other', 'no']);
    expect(S.memo.options[1].to).toBe('pick_payback');
    expect(S.memo.options[2].to).toBe('q1');
  });

  it('shows the message under the name', () => {
    const page = html(<Stacked it={inn} act={noop} commit={noop} onSkip={noop} onBack={noop} />);
    expect(page).toContain('“uber eats”');
  });
});

describe('What was this? as tiles (2026-10-23)', () => {
  const panelOut = { key: 'tx:a', kind: 'panel', txn: { ...out.txn } };
  const panelIn = { key: 'tx:b', kind: 'panel', txn: { ...inn.txn } };
  it('money out: every option laid out as six tiles, no guess first, folded where one idea has two ways', () => {
    const { S } = steps(panelOut, { best: 'moved', cases: [] }, 'all');
    expect(S.all.guess).toBeUndefined();
    const tiles = S.all.options;
    expect(tiles.map((o) => o.label)).toEqual(['A purchase', 'A bill', 'Split with others', 'My own money', 'A loan', 'Not mine']);
    expect(tiles.every((o) => o.icon)).toBe(true);
    expect(S.all_own.options.map((o) => o.v)).toEqual(['moved', 'saved']);
  });
  it('money in: seven tiles, and Pay leads to the kind, where regular pay is', () => {
    const { S } = steps(panelIn, null, 'all');
    expect(S.all.options.map((o) => o.label)).toEqual(
      ['Pay', 'Paid back', 'A refund', 'Reimbursed', 'My own money', 'A loan', 'Not mine']);
    expect(S.all.options[0].to).toBe('kind');
    expect(S.all_loan.options.map((o) => o.v)).toEqual(['borrowed', 'lent_back']);
  });
  it('the card shows the guess and Something else first, the tiles with no guess', async () => {
    const { default: SortCard } = await import('./SortCard.jsx');
    const page = html(<SortCard it={panelIn} commit={noop} mode="all" showHead={false} />);
    // No answers from the server yet: a skeleton, then tiles with no guess.
    expect(page).toContain('nl-skeleton');
  });
});

describe('Answered steps fold and slide (2026-10-23)', () => {
  it('an open row draws its options in a fold, the question in a step that slides in', async () => {
    const { Done: DoneRows, default: SortCard } = await import('./SortCard.jsx');
    const flow = steps(out, null);
    const open = html(<DoneRows path={[{ step: 'q1', v: 'spent' }]} flow={flow} editing={0} onOpen={noop} onPick={noop} />);
    expect(open).toContain('class="nl-fold in"');
    expect(open).toContain('Yes, I spent something');
    const shut = html(<DoneRows path={[{ step: 'q1', v: 'spent' }]} flow={flow} editing={null} onOpen={noop} onPick={noop} />);
    expect(shut).not.toContain('nl-fold');
    const card = html(<SortCard it={out} commit={noop} />);
    expect(card).toContain('class="nl-step"');
  });
});

describe('One savings bucket (2026-10-23)', () => {
  it('saved and taken out of savings save at once, with no account to pick', () => {
    const { S } = steps(out, null);
    expect(S.q1.options.find((o) => o.v === 'saved').to).toBeUndefined();
    expect(S.account).toBeUndefined();
    const all = steps({ key: 'tx:a', kind: 'panel', txn: out.txn }, null, 'all').S;
    expect(all.all_own.options.find((o) => o.v === 'saved')).toMatchObject({ label: 'Into savings', to: undefined });
    const inAll = steps({ key: 'tx:b', kind: 'panel', txn: inn.txn }, null, 'all').S;
    expect(inAll.all_own.options.find((o) => o.v === 'out_of_savings')).toMatchObject({ label: 'Out of savings', to: undefined });
    // Even if the server still says it needs an account.
    const old = steps(out, { cases: [{ key: 'saved', label: 'Put into savings', needs: 'account', group: 'not_spending' }] });
    expect(old.S.what_out).toBeTruthy();
  });
});

describe('Sorted card rows are for a look (2026-10-23)', () => {
  it('reopening an answer with a different pick starts at that step with the new answer', async () => {
    const { resumeFor } = await import('./SortCard.jsx');
    const answers = [{ step: 'q1', v: 'spent', label: 'Spending' }, { step: 'cat', v: 'Home', label: 'Home' }];
    expect(resumeFor(answers, 1)).toEqual({ path: [answers[0]], edit: null, name: '', pick: null });
    expect(resumeFor(answers, 0)).toEqual({ path: [answers[0]], edit: 0, name: '', pick: null });
    expect(resumeFor(answers, 0, 'else')).toEqual({ path: [], edit: null, name: '', pick: { step: 'q1', v: 'else' } });
  });
});

describe('What kind of income? order (2026-10-23)', () => {
  it('Salary and regular pay first, Other last', async () => {
    const { default: Stacked2 } = await import('./SortCard.jsx');
    const page = html(<Stacked2 it={{ ...inn, kind: 'income' }} commit={noop}
                                initialPath={[{ step: 'q1', v: 'income' }]} />);
    const labels = [...page.matchAll(/pk-ctile-label">([^<]+)</g)].map((m) => m[1]);
    expect(labels[0]).toBe('Salary');
    expect(labels[1]).toBe('My regular pay');
    expect(labels[labels.length - 1]).toBe('Other income');
  });
});
