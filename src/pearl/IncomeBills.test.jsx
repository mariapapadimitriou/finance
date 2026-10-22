import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import IncomeBillsFlow, {
  BillForm, BillRow, ExpectedForm, PayForm, billAmount, billSchedule, firstScreen, ordinal,
  payMeta, rentWords,
} from './IncomeBills.jsx';
import { IncomeBillsPage } from '../panels/IncomeBillsPanel.jsx';
import { hubRows } from '../panels/ProfilePanel.jsx';

// THL-127 I-01 to I-06 and Profile › Income and bills.

const html = (el) => renderToStaticMarkup(el);
const text = (el) => html(el).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const calm = (s) => {
  expect(s).not.toMatch(/[−-]\s?\$/);
  expect(s).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(s).not.toMatch(/NaN|undefined|null|\[object/);
};
const primaries = (el) => (html(el).match(/p-btn primary/g) ?? []).length;

const northwind = { payer: 'Northwind Ltd payroll', name: 'Northwind Ltd payroll', amount: 2150,
                    cadence: 'biweekly', last: '2026-10-02', next: '2026-10-16', count: 6 };
const bill = (key, name, amount, day, extra = {}) => ({
  key, name, amount, cadence: 'monthly', day, next: `2026-10-${String(day).padStart(2, '0')}`,
  varies: false, category: 'Other', counts: null, ticked: true, source: 'found', edited: false,
  ...extra,
});
const bills = [
  bill('rent:name:j smith', 'e-Transfer to J. Smith', 1450, 1,
       { ticked: false, counts: false, question: true, recipient: 'J. Smith' }),
  bill('Rogers', 'Rogers', 85, 12),
  bill('Car insurance', 'Car insurance', 190, 20),
  bill('Hydro One', 'Hydro One', 60, 21, { cadence: 'bimonthly', varies: true }),
  bill('Netflix', 'Netflix', 16.49, 22),
  bill('Spotify', 'Spotify', 11.99, 25),
];
const data = {
  today: '2026-10-13', checked: { income: null, bills: null }, pays: [], candidates: [northwind],
  expected: { amount: null, varies: false }, bills,
  rent_question: { key: 'rent:name:j smith', recipient: 'J. Smith', amount: 1450, day: 1 },
  totals: { income: 4300, bills: 1783.48 },
};
const flow = (start, d = data) => <IncomeBillsFlow initial={d} start={start} />;

describe('words', () => {
  it('describes pay and bills as the design does', () => {
    expect(payMeta(northwind)).toBe('$2,150.00 · every second Friday · last on Oct 2');
    expect(billSchedule(bills[1])).toBe('Monthly · around the 12th');
    expect(billSchedule(bills[3])).toBe('Every 2 months · amount varies');
    expect(billAmount(bills[3])).toBe('about $60');
    expect(billAmount(bills[4])).toBe('$16.49');
    expect(ordinal(1)).toBe('1st');
    expect(ordinal(22)).toBe('22nd');
    expect(rentWords(data.rent_question)).toBe(
      'Your $1,450 e-Transfer to J. Smith goes out around the 1st every month. Is it your rent?');
  });

  it('starts on the paycheque, or on I-03 when none was found', () => {
    expect(firstScreen(data)).toBe('pay');
    expect(firstScreen({ ...data, candidates: [] })).toBe('expected');
  });
});

describe('I-01 Is this your paycheque?', () => {
  it('shows the deposit and three answers, none chosen until she picks', () => {
    const t = text(flow('pay'));
    for (const s of ['Your money coming in', 'Is this your paycheque?',
      'We found a deposit that looks like your pay.', 'Northwind Ltd payroll',
      'Looks like pay', 'Yes, that’s my pay', 'The amount or timing is off',
      'No, it’s something else', '+ Add another source of income', 'Continue', '1 of 2',
      'Income first.', 'Knowing when you’re paid lets Pearl work out your Allowance.']) {
      expect(t).toContain(s);
    }
    expect(html(flow('pay'))).not.toContain('pk-choice radio on');
    expect(html(flow('pay'))).toMatch(/disabled=""[^>]*>Continue/);
    expect(primaries(flow('pay'))).toBe(1);
    calm(t);
  });

  it('asks about other candidates as "Also this?"', () => {
    const other = { ...northwind, payer: 'Canada EI', name: 'Canada EI', amount: 640, cadence: 'semimonthly' };
    expect(text(flow('pay', { ...data, candidates: [northwind, other] }))).toContain('Also this?');
    expect(text(flow('pay'))).not.toContain('Also this?');
  });
});

describe('I-02 Edit your pay', () => {
  it('is prefilled from the deposit', () => {
    const t = html(<PayForm pay={northwind} onSave={() => {}} onCancel={() => {}} />);
    for (const s of ['Tell us about your pay', 'Name', 'Usual amount after tax',
      'Use what lands in your account.', 'How often', 'Next pay date', 'Save', 'Cancel']) {
      expect(t).toContain(s);
    }
    expect(t).toContain('value="$2,150.00"');
    expect(t).toContain('value="2026-10-16"');
    expect(t).toMatch(/<option value="biweekly" selected="">Every 2 weeks<\/option>/);
    expect(primaries(<PayForm pay={northwind} onSave={() => {}} onCancel={() => {}} />)).toBe(1);
  });
});

describe('I-03 No pay found', () => {
  it('asks for the income she expects', () => {
    const t = text(flow('expected', { ...data, candidates: [] }));
    for (const s of ['We didn’t spot a regular paycheque',
      'That’s common if you’re new to a job, freelance, or paid in cash. Tell us roughly what you expect.',
      'Expected income each month', 'After tax. A rough number is fine.',
      'My income varies month to month', 'We’ll plan with a careful estimate', 'Continue',
      'Skip for now']) {
      expect(t).toContain(s);
    }
    calm(t);
  });

  it('shows an amount she already gave', () => {
    const t = html(<ExpectedForm expected={{ amount: 3800, varies: true }} onSave={() => {}} />);
    expect(t).toContain('value="$3,800"');
    expect(t).toMatch(/pk-choice checkbox on/);
  });
});

describe('I-04 Are these your regular bills?', () => {
  it('lists the bills, asks about rent, and counts what is ticked', () => {
    const t = text(flow('bills'));
    for (const s of ['Your regular bills', 'Are these your regular bills?',
      'Untick anything that isn’t a regular bill.', rentWords(data.rent_question),
      'Yes, it’s my rent', 'e-Transfer to J. Smith', 'Monthly · around the 1st', '$1,450.00',
      'Rogers', 'Car insurance', 'about $60', 'Every 2 months · amount varies', 'Netflix',
      'Spotify', '+ Add a bill we missed', 'Confirm 5 bills', '2 of 2', 'Then what goes out.']) {
      expect(t).toContain(s);
    }
    expect(primaries(flow('bills'))).toBe(1);
    calm(t);
  });

  it('hides the rent question when there is no pattern, and says when nothing is ticked', () => {
    const none = { ...data, rent_question: null, bills: bills.slice(1).map((b) => ({ ...b, ticked: false })) };
    const t = text(flow('bills', none));
    expect(t).not.toContain('Is it your rent?');
    expect(t).toContain('Continue without bills');
    expect(text(flow('bills', { ...data, bills: [bills[1]], rent_question: null }))).toContain('Confirm 1 bill');
  });

  it('draws an unticked row muted, with Edit', () => {
    const row = html(<BillRow bill={bills[0]} ticked={false} onTick={() => {}} onEdit={() => {}} />);
    expect(row).toContain('ib-row off');
    expect(row).toContain('Edit');
  });
});

describe('I-05 Add or edit a bill', () => {
  it('adds a bill', () => {
    const t = text(flow('bill'));
    for (const s of ['Your regular bills', 'Add a bill', 'Name', 'Amount', 'How often',
      'Next due date', 'The amount changes each time', 'Save bill', 'Cancel']) {
      expect(t).toContain(s);
    }
    expect(t).not.toContain('Remove this bill');
  });

  it('editing offers Remove this bill as text, not a second primary', () => {
    const el = <BillForm bill={bills[1]} onSave={() => {}} onCancel={() => {}} onRemove={() => {}} />;
    expect(text(el)).toContain('Remove this bill');
    expect(text(el)).toContain('Edit a bill');
    expect(primaries(el)).toBe(1);
  });
});

describe('I-06 All set', () => {
  it('says income and bills each month in whole dollars', () => {
    const t = text(flow('done'));
    for (const s of ['That’s everything we need', 'Pearl can now work out your Allowance each month.',
      'Income each month', '$4,300', 'Regular bills', '$1,783', 'Continue',
      'You can change these any time in Profile › Income and bills.', 'Ready.']) {
      expect(t).toContain(s);
    }
    calm(t);
  });

  it('never shows $0', () => {
    const t = text(flow('done', { ...data, totals: { income: null, bills: 0 } }));
    expect(t).toContain('Not set yet');
    expect(t).toContain('None yet');
    calm(t);
  });
});

describe('Profile › Income and bills', () => {
  const confirmed = {
    ...data, candidates: [], rent_question: null,
    pays: [{ id: 'p1', payer: 'Northwind Ltd payroll', name: 'Northwind Ltd payroll', amount: 2150,
             cadence: 'biweekly', next: '2026-10-16' }],
    bills: [bills[1], { ...bills[4], ticked: false, counts: false },
            bill('added:b1', 'Gym membership', 45, 1, { source: 'added', counts: true })],
  };

  it('is the hub row under Money', () => {
    const money = hubRows({}, {})[0];
    expect(money.rows.map((r) => r.name)).toContain('Income and bills');
    expect(money.rows.find((r) => r.name === 'Income and bills').key).toBe('income');
    expect(JSON.stringify(hubRows({}, {}))).not.toContain('commitments');
  });

  it('shows the confirmed pay and bills, what is not counted, and Check again', () => {
    const t = text(<IncomeBillsPage data={confirmed} onOpen={() => {}} onTick={() => {}}
                                    onRent={() => {}} onCheck={() => {}} />);
    for (const s of ['Profile', 'Income and bills', 'Income each month', '$4,300', 'Regular bills',
      'Northwind Ltd payroll', '$2,150.00 · every second Friday · next on Oct 16',
      '+ Add another source of income', 'Rogers', 'Gym membership', 'Not counted', 'Netflix',
      '+ Add a bill we missed', 'Check again']) {
      expect(t).toContain(s);
    }
    calm(t);
  });

  it('shows expected income when no pay is confirmed', () => {
    const t = text(<IncomeBillsPage data={{ ...confirmed, pays: [], expected: { amount: 3800, varies: true } }}
                                    onOpen={() => {}} />);
    expect(t).toContain('Your own amount');
    expect(t).toContain('$3,800 a month after tax · varies, so we plan carefully');
  });

  it('shows Pearl’s estimate from the last 3 months when she gave no amount', () => {
    const t = text(<IncomeBillsPage data={{ ...confirmed, pays: [],
                                            expected: { amount: null, varies: false, estimate: 3900 } }}
                                    onOpen={() => {}} />);
    expect(t).toContain('Pearl’s estimate');
    expect(t).toContain('$3,900 a month · the average of your last 3 months');
    expect(t).toContain('Use my own amount');
  });

  it('her own amount comes first, over her pay', () => {
    const t = text(<IncomeBillsPage data={{ ...confirmed,
                                            expected: { amount: 6000, varies: false, estimate: 3900 } }}
                                    onOpen={() => {}} />);
    expect(t.indexOf('Your own amount')).toBeLessThan(t.indexOf(confirmed.pays[0].name));
    expect(t).toContain('used instead of Pearl’s estimate');
  });

  it('says plainly when nothing is confirmed', () => {
    const t = text(<IncomeBillsPage data={{ ...confirmed, pays: [], bills: [],
                                            totals: { income: null, bills: 0 } }} onOpen={() => {}} />);
    expect(t).toContain('No income confirmed yet');
    expect(t).toContain('No regular bills counted yet.');
    calm(t);
  });
});
