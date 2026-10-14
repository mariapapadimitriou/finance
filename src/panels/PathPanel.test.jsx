import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PathPage, stepDetail } from './PathPanel.jsx';

const html = (el) => renderToStaticMarkup(el);

const build = {
  phase: 'build', step: 2, of: 2, protect_done: true,
  phases: [{ key: 'protect', label: 'Protect', state: 'done' },
           { key: 'build', label: 'Build', state: 'now' },
           { key: 'unveil', label: 'Unveil', state: 'ahead' }],
  steps: [{ key: 'first_stop', label: 'Reach your Anchor’s first stop', done: true, first_stop: 500 },
          { key: 'full', label: 'Fill your Anchor', done: false, target: 2150 }],
  also: [{ key: 'saved_more', label: 'Save more than you spend in 2 of the last 3 months',
           done: true, count: 2, of: 3 },
         { key: 'cards', label: 'Keep card balances from growing', done: false }],
  next: { text: 'Next: add to your Anchor.', label: 'Add to your Anchor', action: 'goals' },
};

describe('Path page (GR-01)', () => {
  it('shows the phases, this phase’s steps, what also counts, and the next step', () => {
    const out = html(<PathPage path={build} onAction={() => {}} />);
    for (const text of ['Growth', 'Done', 'Now', 'Ahead', 'Steps in Build', 'Build · step 2 of 2',
                        'Reach your Anchor’s first stop', 'One month of Essentials: $2,150',
                        'Also counts toward Build', 'A card balance grew last month',
                        'Your next step', 'add to your Anchor.', 'Ready to invest']) {
      expect(out).toContain(text);
    }
    expect((out.match(/pk-btn primary/g) || []).length).toBe(1);
    expect(out).not.toMatch(/NaN|undefined|\$0(?![.,\d])/);
  });

  it('Ready to invest waits for Protect', () => {
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
    expect(stepDetail({ key: 'first_stop', done: false, first_stop: 500 }, true)).toBe('Your first stop is $500');
    expect(stepDetail({ key: 'invest', done: false }, true)).toBe('In progress');
    expect(stepDetail({ key: 'invest', done: true }, false)).toBe('Done');
  });
});
