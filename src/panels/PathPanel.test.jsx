import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PathPage, stepDetail } from './PathPanel.jsx';

const html = (el) => renderToStaticMarkup(el);

const build = {
  phase: 'build', step: 2, of: 2, protect_done: true,
  phases: [{ key: 'protect', label: 'The basics', text: 'Income, bills and Essentials covered', state: 'done' },
           { key: 'build', label: 'Your Anchor', text: 'Three months of Essentials, for big surprises', state: 'now' },
           { key: 'unveil', label: 'Grow your money', text: 'Your first investment account', state: 'ahead' }],
  steps: [{ key: 'setup', label: 'Set up your Anchor', done: true, started_on: '2026-09-14' },
          { key: 'full', label: 'Grow your Anchor to 3 months', done: false, target: 8700, counted: 5470,
            months: 1.9, usual: 2900 }],
  also: [{ key: 'saved_more', label: 'Save more than you spend in 2 of the last 3 months',
           done: true, count: 2, of: 3 },
         { key: 'cards', label: 'Keep card balances from growing', done: false }],
  next: { text: 'Next: grow your Anchor to 3 months of Essentials, so a big surprise like a car repair doesn’t land on your credit card.',
          label: 'See your Anchor', action: 'goals' },
};

describe('Path page (GR-01, without phase names)', () => {
  it('shows the three stretches, this one’s steps, what also counts, and the next step', () => {
    const out = html(<PathPage path={build} onAction={() => {}} />);
    for (const text of ['Wins', 'Done', 'Now', 'Ahead', 'The basics', 'Your Anchor', 'Grow your money',
                        'Three months of Essentials, for big surprises', 'Steps · Your Anchor',
                        'Your Anchor · step 2 of 2', 'Set up your Anchor', 'Done in September',
                        'Grow your Anchor to 3 months', '$5,470 · 1.9 of 3 months',
                        'Also counts', 'A card balance grew last month',
                        'Your next step', 'grow your Anchor to 3 months of Essentials', 'Ready to invest',
                        'Open since the basics were done']) {
      expect(out).toContain(text);
    }
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
    expect(out).not.toMatch(/NaN|undefined|\$0(?![.,\d])/);
    expect(out).not.toMatch(/Protect|Build|Unveil|Shine/);
  });

  it('Ready to invest waits for the basics', () => {
    const protect = { ...build, phase: 'protect', protect_done: false, also: [],
                      phases: build.phases.map((p, i) => ({ ...p, state: ['now', 'ahead', 'ahead'][i] })),
                      steps: [{ key: 'income', label: 'Confirm your income', done: false }],
                      step: 1, of: 3,
                      next: { text: 'Next: add your income.', label: 'Add your income', action: 'income' } };
    expect(html(<PathPage path={protect} onAction={() => {}} />)).not.toContain('Ready to invest');
  });

  it('each step says where it stands in her numbers', () => {
    expect(stepDetail({ key: 'essentials', done: false, month: '2026-09', income: 4300, essentials: 2000,
                        estimate: true }, true))
      .toBe('In September: $4,300 expected (what you told Pearl), $2,000 went on Essentials');
    expect(stepDetail({ key: 'essentials', done: false, month: '2026-09', income: 1500, essentials: 2000 }, true))
      .toBe('In September: $1,500 came in, $2,000 went on Essentials');
    expect(stepDetail({ key: 'setup', done: false }, true)).toBe('Pick the savings accounts that make it up');
    expect(stepDetail({ key: 'setup', done: true, started_on: '2026-09-14' }, false)).toBe('Done in September');
    expect(stepDetail({ key: 'full', done: false, target: 8700, counted: 0 }, true))
      .toBe('Three months of Essentials: $8,700');
    expect(stepDetail({ key: 'invest', done: false }, true)).toBe('In progress');
    expect(stepDetail({ key: 'invest', done: true }, false)).toBe('Done');
  });
});
