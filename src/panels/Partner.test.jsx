import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { BeforeYouGo, OpenedOne, PartnerCard, WelcomeBack } from './Partner.jsx';
import { ReadyPage, checklistRows } from './Unveil.jsx';

// THL-136 (post-MVP) GR-19 Before you go, GR-20 Welcome back, GR-21 I opened
// an account, GR-22 No partner yet, GR-23 Before Protect is done.

const html = (el) => renderToStaticMarkup(el);
const BAD = /NaN|undefined|\$0(?![.,\d])|\[object/;
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;
const nav = { show: () => {}, onTab: () => {}, toGoals: () => {}, toLearn: () => {}, toStep: () => {} };

const checklist = [
  { key: 'protect', done: true },
  { key: 'anchor', done: false, started: true, counted: 62000, target: 215000 },
  { key: 'cards', done: true, months: 3, cards: 1, grew_in: null },
  { key: 'basics', done: false, available: true, read: 2, of: 5, next: 'index-funds-etfs' },
];
const ready = (partner, extra = {}) => ({
  checklist, report: null, partner,
  path: { phases: [] }, types: [], ...extra,
});
const PARTNER = { configured: true, name: 'Example Invest', welcome: false, notify: false };
const NONE = { configured: false, name: null, welcome: false, notify: false };

describe('GR-16 with a partner configured', () => {
  it('the partner card, with the disclosure line, and a way to report any account', () => {
    const out = html(<ReadyPage data={ready(PARTNER)} nav={nav} />);
    for (const text of ['When you’re ready', 'Open your first account',
                        'With Example Invest, a registered investment provider. They handle the account and any advice.',
                        'Pearl may be paid if you open an account.', 'See how it works',
                        'I’ve opened one elsewhere', '2 of 5 modules']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).not.toMatch(BAD);
  });
});

describe('GR-19 Before you go', () => {
  it('three steps, then the disclosure above the button, every time', () => {
    const out = html(<BeforeYouGo name="Example Invest" onGo={() => {}} onClose={() => {}} />);
    for (const text of ['Before you go', 'Open an account with Example Invest',
                        'You’ll leave Pearl for Example Invest’s site', 'A registered investment provider in Canada.',
                        'Example Invest does the rest', 'Pearl doesn’t recommend investments.',
                        'Come back and tell us', 'We’ll mark the milestone done.',
                        'Pearl may be paid if you open an account.',
                        'We never share your transactions or balances with Example Invest.',
                        'Not now', 'Continue to Example Invest']) {
      expect(out).toContain(text);
    }
    expect(out.indexOf('may be paid')).toBeLessThan(out.indexOf('Continue to Example Invest'));
    expect(out).toContain('role="dialog"');
    expect(out).toContain('aria-modal="true"');
    expect(primaries(out)).toBe(1);
  });
});

describe('GR-20 Welcome back', () => {
  it('asks once she’s back, and the banner holds the page’s one primary', () => {
    const out = html(<ReadyPage data={ready({ ...PARTNER, welcome: true })} nav={nav} />);
    for (const text of ['Welcome back', 'Did you open an account with Example Invest?', 'Not yet',
                        'Yes, I opened one']) {
      expect(out).toContain(text);
    }
    expect(primaries(out)).toBe(1);
    expect(out).toMatch(/pk-btn secondary[^"]*"[^>]*>See how it works/);
  });

  it('the ?from=partner return asks too', () => {
    expect(html(<ReadyPage data={ready(PARTNER)} nav={nav} returned />)).toContain('Welcome back');
  });

  it('never once she’s told Pearl, and never without a partner', () => {
    const told = ready({ ...PARTNER, welcome: true }, { report: { type: 'tfsa', label: 'TFSA' } });
    expect(html(<ReadyPage data={told} nav={nav} returned />)).not.toContain('Welcome back');
    expect(html(<ReadyPage data={ready(NONE)} nav={nav} returned />)).not.toContain('Welcome back');
  });

  it('the banner on its own', () => {
    const out = html(<WelcomeBack name="Example Invest" onYes={() => {}} onNotYet={() => {}} />);
    expect(primaries(out)).toBe(1);
  });
});

describe('GR-21 I opened an account', () => {
  it('confirms without asking what or how much', () => {
    const out = html(<OpenedOne onConfirm={() => {}} onClose={() => {}} />);
    for (const text of ['You opened your first investment account',
                        'We’ll mark the milestone done. We don’t see what you invest in or how much, and we won’t ask.',
                        'Go back', 'Mark it done']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(/<input|password|login/i);
    expect(primaries(out)).toBe(1);
  });
});

describe('GR-22 No partner yet', () => {
  it('a sign-up, and the self-report for an account opened elsewhere', () => {
    const out = html(<ReadyPage data={ready(NONE)} nav={nav} />);
    for (const text of ['Coming soon', 'We’re choosing a partner',
                        'Pearl will only work with a provider registered in Canada.',
                        'Tell me when Pearl partners with a provider', 'I opened an account elsewhere']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(/may be paid|See how it works/);
    expect(primaries(out)).toBe(1);
  });

  it('once she’s signed up, it says so', () => {
    const out = html(<PartnerCard partner={{ ...NONE, notify: true }} protectDone />);
    expect(out).toContain('You’re on the list.');
    expect(out).not.toContain('Tell me when Pearl partners');
  });
});

describe('GR-23 Before Protect is done', () => {
  const early = [
    { key: 'protect', done: false, left: 1, next: 'essentials' },
    { key: 'anchor', done: false, started: false, counted: 0, target: 0 },
    { key: 'cards', done: true, months: 3, cards: 1, grew_in: null },
    { key: 'basics', done: false, available: true, read: 0, of: 5, next: 'tfsa-rrsp-fhsa' },
  ];

  it('the checklist stays visible; the partner step says what opens it, with no lock', () => {
    const out = html(<ReadyPage data={ready(PARTNER, { checklist: early })} nav={nav} />);
    for (const text of ['The basics are done', '1 step left: your income covers your Essentials', 'See the step',
                        'Your Anchor is under way', 'Comes after the basics', 'Read the basics', '0 of 5 modules',
                        'Start', 'Opens once the basics are done', 'Open your first account',
                        'Once your income covers your Essentials for a month, this opens. Learning is open now.',
                        'Start learning']) {
      expect(out).toContain(text);
    }
    expect(out).not.toMatch(/lock|See how it works|may be paid/i);
    expect(out).not.toMatch(BAD);
  });

  it('the rows', () => {
    const rows = checklistRows(early, nav);
    expect(rows[0].link.text).toBe('See the step');
    expect(rows[1]).toMatchObject({ todo: true, detail: 'Comes after the basics', link: null });
    expect(rows[3]).toMatchObject({ detail: '0 of 5 modules' });
    expect(rows[3].link.text).toBe('Start');
    const more = checklistRows([{ key: 'protect', done: false, left: 3, next: 'income' }], nav);
    expect(more[0].detail).toBe('3 steps left, starting with: confirm your income');
  });

  it('Read the basics ticks at five', () => {
    const rows = checklistRows([{ key: 'basics', done: true, read: 5, of: 5, next: null }], nav);
    expect(rows[0]).toMatchObject({ done: true, detail: 'All 5 modules read', link: null });
  });
});
