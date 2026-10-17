// Learn's five "Before you invest" modules (Pearl THL-134 GR-15, module
// content: a draft for securities counsel). The ids, screen counts and quick-
// check answers are mirrored in finance/learn.py, which keeps her place.
//
// Where the words come from:
// * Each module's title, subtitle, minutes and screens 1 to 3 are GR-15's
//   copy (Pearl UX Flows › THL-134), with each screen's overline as its title.
//   Screen 2 of the first module is GR-12's ("How each one is taxed", the
//   lead line and the table). The fees illustration's figures are GR-15's;
//   they are laid out as a table here.
// * Each quick check's question is GR-15's (the first is GR-13's wording),
//   and the first module's "That's it" is GR-13's.
// * Written for the build, for counsel to review with the rest: the answer
//   options other than the first module's, every other explanation (the
//   "That's it" and the "Close!" lines), each module's one-line done state
//   other than the first (GR-14's), and the Allowance explainer.
//
// The rules (THL-134, THL-13): general, not tailored; no fund, security or
// provider named; no yearly limit hard-coded except the FHSA's $8,000 and
// $40,000, which counsel is to confirm. Not advice.

export const DISCLAIMER = 'General information only, not financial advice.';

export const MODULES = [
  {
    id: 'tfsa-rrsp-fhsa',
    title: 'TFSA, RRSP and FHSA',
    sub: 'Three accounts, three jobs',
    minutes: 4,
    done: 'You know what each account is for and how each one is taxed.',
    screens: [
      { title: 'Three accounts, three jobs',
        body: ['They’re containers, not investments. You decide what goes inside them, and each has a different job.'] },
      { title: 'How each one is taxed',
        body: ['All three let your money grow without tax each year. The difference is when tax shows up.'],
        table: {
          caption: 'How the TFSA, RRSP and FHSA are taxed',
          cols: ['TFSA', 'RRSP', 'FHSA'],
          rows: [
            ['Best for', 'Anything: flexible saving', 'Retirement', 'Your first home'],
            ['When you put money in', 'No tax deduction', 'Lowers your taxable income', 'Lowers your taxable income'],
            ['When you take it out', 'Tax-free', 'Taxed as income', 'Tax-free for a first home'],
            ['How much', 'Room set each year; unused room carries over', 'Based on last year’s income',
             '$8,000 a year, $40,000 in total'],
          ],
        } },
      { title: 'Which one first?',
        body: ['It depends on your goal. A first home soon: many people start with an FHSA. Saving for later in life: an RRSP. Want flexibility: a TFSA.',
               'This is general, not advice for you.'] },
    ],
    check: {
      question: 'Which account can lower your taxes when you put money in, and let you take it out tax-free for your first home?',
      options: [{ key: 'tfsa', label: 'TFSA' }, { key: 'rrsp', label: 'RRSP' }, { key: 'fhsa', label: 'FHSA' }],
      answer: 'fhsa',
      right: 'The FHSA does both, as long as the money goes toward a qualifying first home.',
      close: {
        tfsa: 'A TFSA is tax-free when you take money out, but putting money in doesn’t lower your taxes. The FHSA does both, for a qualifying first home.',
        rrsp: 'An RRSP lowers your taxes when you put money in, but what you take out is usually taxed as income. The FHSA does both, for a qualifying first home.',
      },
    },
  },
  {
    id: 'index-funds-etfs',
    title: 'Index funds and ETFs',
    sub: 'One fund, many companies',
    minutes: 4,
    done: 'You know what index funds and ETFs are, and why people use them.',
    screens: [
      { title: 'One fund, many companies',
        body: ['An index fund holds a small slice of every company in a list (an index), such as the largest companies in Canada.'] },
      { title: 'What an ETF is',
        body: ['An exchange-traded fund is a fund you buy and sell like a single share. Many ETFs follow an index.'] },
      { title: 'Why people use them',
        body: ['Your money is spread across many companies, fees are often low, and there’s little to manage. Their value still goes up and down.'] },
    ],
    check: {
      question: 'True or false: an index fund puts all your money into one company.',
      options: [{ key: 'true', label: 'True' }, { key: 'false', label: 'False' }],
      answer: 'false',
      right: 'An index fund spreads your money across every company in its index.',
      close: {
        true: 'An index fund holds a small slice of every company in its index, so your money is spread out rather than in one company.',
      },
    },
  },
  {
    id: 'risk-time-horizon',
    title: 'Risk and time horizon',
    sub: 'Why when you need the money matters',
    minutes: 4,
    done: 'You know why when you need the money matters, and that your comfort counts.',
    screens: [
      { title: 'Values move',
        body: ['Investments go up and down. Some years they go down, sometimes a lot.'] },
      { title: 'Time changes the picture',
        body: ['Money you’ll need in the next couple of years is often kept somewhere steady, like your Anchor. Money for many years from now has more time to recover from dips.'] },
      { title: 'Your comfort counts',
        body: ['Think about how you’d feel if your balance dropped by a fifth for a while. Providers ask questions like this to match you to a mix.'] },
    ],
    check: {
      question: 'You’ll need $3,000 for rent next spring. Where does that money usually live?',
      options: [{ key: 'steady', label: 'Somewhere steady, like your Anchor' },
                { key: 'invested', label: 'Invested, so it can grow' }],
      answer: 'steady',
      right: 'Money you’ll need within a year or two is often kept somewhere steady, so a dip can’t touch it.',
      close: {
        invested: 'Investments can drop just before you need the money. Money for the next year or two is often kept somewhere steady, like your Anchor.',
      },
    },
  },
  {
    id: 'fees',
    title: 'Fees',
    sub: 'Small numbers that add up',
    minutes: 3,
    done: 'You know where fees show up, and how a small yearly fee adds up.',
    screens: [
      { title: 'Small numbers, big over time',
        body: ['Fees are a yearly percentage. A difference of 1 to 2% a year can add up to thousands over 20 years.'] },
      { title: 'An illustration',
        body: ['$10,000 growing 5% a year for 20 years. Illustrative only.'],
        table: {
          caption: '$10,000 growing 5% a year for 20 years, illustrative',
          cols: ['After 20 years'],
          rows: [
            ['Before fees', 'About $26,500'],
            ['With a 0.25% yearly fee', 'About $25,300'],
            ['With a 2% yearly fee', 'About $18,100'],
          ],
        } },
      { title: 'Where fees show up',
        body: ['In the fund’s yearly cost (MER), trading commissions, and account fees. Ask for the total yearly cost as one percentage.'] },
    ],
    check: {
      question: 'Which matters more over 20 years?',
      options: [{ key: 'one_time', label: 'A one-time $10 fee' }, { key: 'yearly', label: 'A 1% yearly fee' }],
      answer: 'yearly',
      right: 'A 1% yearly fee is taken every year from a growing balance, so over 20 years it can add up to thousands.',
      close: {
        one_time: 'A $10 fee is paid once. A 1% yearly fee is taken every year from a growing balance, so over 20 years it usually costs far more.',
      },
    },
  },
  {
    id: 'robo-or-self-directed',
    title: 'Robo-advisor or self-directed',
    sub: 'Two ways to invest, neither wrong',
    minutes: 4,
    done: 'You know the two ways to invest, and that neither is wrong.',
    screens: [
      { title: 'Two ways to invest',
        body: ['With a robo-advisor you answer some questions and it builds and rebalances a mix for you, for a fee. Self-directed means you choose and buy investments yourself.'] },
      { title: 'Trade-offs',
        body: ['Robo-advisor: less effort, a management fee, less control. Self-directed: more effort, often lower costs, full control.'] },
      { title: 'Neither is wrong',
        body: ['The best choice is the one you’ll stick with. You can start one way and change later.'] },
    ],
    check: {
      question: 'Which option rebalances your mix for you?',
      options: [{ key: 'robo', label: 'A robo-advisor' }, { key: 'self', label: 'Self-directed investing' }],
      answer: 'robo',
      right: 'A robo-advisor builds your mix and keeps it in balance, for a fee.',
      close: {
        self: 'With self-directed investing you rebalance yourself. A robo-advisor does it for you, for a fee.',
      },
    },
  },
];

export const moduleById = (id) => MODULES.find((m) => m.id === id) ?? null;

// The two explainers under the modules (GR-11): how Allowance works
// (THL-46) is a page here; how we protect you (THL-115) is Profile's page.
export const SAFE_TO_SPEND = {
  id: 'safe-to-spend',
  title: 'How Allowance works',
  body: [
    'Allowance is what’s left for the rest of the month once the things you can’t skip are covered.',
    'We start with what comes in this month: the pay we found, or the income you told us.',
    'Then we take away your bills still to come, what you’ve already spent, and anything you’re setting aside for your Anchor or a saving goal.',
    'What’s left is Allowance. It changes as money comes in and goes out, and Home shows how we worked it out.',
  ],
};
