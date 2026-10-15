import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Check, Explainer, LearnPage, ModuleDone, ModulePage, moduleStatus } from './LearnPanel.jsx';
import { DISCLAIMER, MODULES, SAFE_TO_SPEND, moduleById } from './learnModules.js';

// THL-134 GR-11 Learn, GR-12 a module screen, GR-13 Check yourself, GR-14
// Module done, and the content rules the modules follow.

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\[object/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;
const nav = { onTab: () => {}, open: () => {}, list: () => {}, ready: () => {}, save: async () => ({}) };

const state = (overrides = {}) => ({
  read: 1, of: 5, next: 'index-funds-etfs',
  modules: MODULES.map((m) => ({ id: m.id, screens: 4, screen: 0, done: false, answer: null,
                                 ...(overrides[m.id] ?? {}) })),
});
const data = state({ 'tfsa-rrsp-fhsa': { screen: 4, done: true, answer: 'fhsa' },
                     'index-funds-etfs': { screen: 2 } });

describe('GR-11 Learn', () => {
  it('lists the five modules with what she’s read, and the two explainers', () => {
    const out = html(<LearnPage data={data} nav={nav} />);
    for (const text of ['Learn at your pace', 'Save', 'Before you invest', '1 of 5 read',
                        'TFSA, RRSP and FHSA', 'Three accounts, three jobs', 'Read',
                        'Index funds and ETFs', 'One fund, many companies', '2 of 4',
                        'Risk and time horizon', 'Why when you need the money matters',
                        'Fees', 'Small numbers that add up', '3 min',
                        'Robo-advisor or self-directed', 'Two ways to invest, neither wrong', 'Start',
                        'Explainer', 'How safe-to-spend works', 'How we protect you', DISCLAIMER]) {
      expect(out).toContain(text);
    }
    expect(out).toContain('>Learn</h1>');
    expect(out).toContain('> Save');                       // the way back to Save
    expect(out).not.toContain('class="in-tabs"');
    expect(out).not.toContain('disabled');
    expect(out).not.toMatch(BAD);
  });

  it('a module is new, part-read or read', () => {
    expect(moduleStatus({ screen: 0, done: false })).toBe('new');
    expect(moduleStatus({ screen: 3, done: false })).toBe('reading');
    expect(moduleStatus({ screen: 4, done: true })).toBe('read');
  });
});

describe('GR-12 a module screen', () => {
  it('back to Learn, four segments, one idea, Back and Next', () => {
    const m = moduleById('tfsa-rrsp-fhsa');
    const out = html(<ModulePage module={m} data={data} nav={nav} initial={2} />);
    for (const text of ['Learn', 'TFSA, RRSP and FHSA · 2 of 4', 'How each one is taxed',
                        'All three let your money grow without tax each year. The difference is when tax shows up.',
                        'Best for', 'Anything: flexible saving', 'Retirement', 'Your first home',
                        'When you put money in', 'No tax deduction', 'Lowers your taxable income',
                        'When you take it out', 'Tax-free', 'Taxed as income', 'Tax-free for a first home',
                        'How much', 'Room set each year; unused room carries over', 'Based on last year’s income',
                        '$8,000 a year, $40,000 in total', 'Back', 'Next', DISCLAIMER]) {
      expect(out).toContain(text);
    }
    expect((out.match(/<span class="on">/g) || []).length).toBe(2);
    expect(out).toContain('<caption class="pk-sr">');
    expect(primaries(out)).toBe(1);
  });

  it('picks up where she left off', () => {
    const m = moduleById('index-funds-etfs');
    expect(html(<ModulePage module={m} data={data} nav={nav} />)).toContain('What an ETF is');
  });
});

describe('GR-13 Check yourself', () => {
  const m = moduleById('tfsa-rrsp-fhsa');

  it('one question, no score; the right answer says why', () => {
    const out = html(<Check module={m} answer="fhsa" onChoose={() => {}} />);
    for (const text of ['Quick check', m.check.question, 'TFSA', 'RRSP', 'FHSA', 'That’s it',
                        'The FHSA does both, as long as the money goes toward a qualifying first home.']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(/score|wrong|correct|\d+%/i);
  });

  it('another answer is “Close!”, never “Wrong”', () => {
    const out = html(<Check module={m} answer="rrsp" onChoose={() => {}} />);
    expect(out).toContain('Close!');
    expect(out).toContain('usually taxed as income');
  });

  it('nothing is explained until she answers; Finish is the one primary', () => {
    expect(html(<Check module={m} answer={null} onChoose={() => {}} />)).not.toContain('lr-explain');
    const out = html(<ModulePage module={m} data={state()} nav={nav} initial={4} />);
    expect(out).toContain('Finish');
    expect(primaries(out)).toBe(1);
  });
});

describe('GR-14 Module done', () => {
  const m = moduleById('tfsa-rrsp-fhsa');

  it('what she knows, the checklist tick, and the next module', () => {
    const out = html(<ModuleDone module={m} data={data} nav={nav} from="" />);
    for (const text of ['You finished TFSA, RRSP and FHSA',
                        'You know what each account is for and how each one is taxed.',
                        'Ready to invest checklist · modules read 1 of 5', 'Up next', 'Index funds and ETFs',
                        '4 min · you’re halfway', 'Continue']) {
      expect(out).toContain(text);
    }
    expect(out).not.toContain('Back to Ready to invest');
    expect(primaries(out)).toBe(1);
  });

  it('“Back to Ready to invest” only when she came from the checklist', () => {
    expect(html(<ModuleDone module={m} data={data} nav={nav} from="ready" />)).toContain('Back to Ready to invest');
  });

  it('with all five read', () => {
    const all = state(Object.fromEntries(MODULES.map((x) => [x.id, { done: true, screen: 4 }])));
    const out = html(<ModuleDone module={m} data={{ ...all, read: 5 }} nav={nav} />);
    expect(out).toContain('You’ve read all five modules');
    expect(out).toContain('modules read 5 of 5');
  });
});

describe('the modules (GR-15, a draft for counsel)', () => {
  it('five, each three screens and a quick check whose answer is one of its options', () => {
    expect(MODULES.map((m) => m.id)).toEqual(['tfsa-rrsp-fhsa', 'index-funds-etfs', 'risk-time-horizon',
                                              'fees', 'robo-or-self-directed']);
    for (const m of MODULES) {
      expect(m.screens).toHaveLength(3);
      expect(m.check.options.map((o) => o.key)).toContain(m.check.answer);
      for (const o of m.check.options) {
        if (o.key !== m.check.answer) expect(m.check.close[o.key], `${m.id} ${o.key}`).toBeTruthy();
      }
    }
  });

  it('general, not tailored: no provider, fund or recommendation named', () => {
    const text = JSON.stringify(MODULES) + JSON.stringify(SAFE_TO_SPEND);
    expect(text).not.toMatch(/Wealthsimple|Questrade|Vanguard|iShares|BlackRock|RBC|TD |Scotia|BMO|CIBC|you should/i);
    expect(text).toContain('This is general, not advice for you.');
    expect(text).toContain('Illustrative only');
  });

  it('the fees illustration adds up: $10,000 at 5% for 20 years', () => {
    const grow = (rate) => 10000 * (1 + rate) ** 20;
    expect(Math.round(grow(0.05) / 100) * 100).toBe(26500);
    expect(Math.round(grow(0.0475) / 100) * 100).toBe(25300);
    expect(Math.round(grow(0.03) / 100) * 100).toBe(18100);
  });

  it('the safe-to-spend explainer', () => {
    const out = html(<Explainer onBack={() => {}} onHome={() => {}} />);
    expect(out).toContain('How safe-to-spend works');
    expect(out).toContain('See yours on Home');
  });
});
