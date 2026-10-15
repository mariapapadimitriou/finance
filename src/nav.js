// Where everything is, and what it is called.
//
// One module, imported by the shell that draws the navigation and by the
// panels that link across it.

// Every panel the app can show, keyed the way it always was.
//
// These used to be twelve top-level destinations plus a hidden one, which on a
// phone was a scrolling strip nobody could hold in their head, and which put
// the four surfaces you touch once at setup beside the two you open daily.
// They are grouped below instead. The keys are unchanged, so every
// `onTab('piggy')` in a panel still works — `resolve` turns a panel key into
// the group that now contains it.
export const PANELS = {
  // Home (Pearl THL-125, GR-05): safe to spend for the month and how it was
  // worked out. Where the app lands.
  home:          { label: 'Home',
                   hint: 'What’s safe to spend this month, and how we worked it out' },
  // Cash flow › Budgets (THL-168 B-01): every category, from her usual month.
  budgets:       { label: 'Budgets',
                   hint: 'A budget for every category, starting at your usual month' },
  // Wins › Path (THL-129 GR-01): the milestone path and the next step.
  path:          { label: 'Path',
                   hint: 'Where you are on your path, and the one next step' },
  // Cash flow › Insights (THL-186, THL-196 GR-28, at /cashflow/insights): the
  // month against her usual, in pictures, with a detail view behind each.
  insights:      { label: 'Insights',
                   hint: 'Your month against your usual, and where the money went' },
  // Cash flow › Debts (THL-49 D-02): every balance owed, from before Pearl too.
  debts:         { label: 'Debts',
                   hint: 'Everything you owe, and the minimums counted as bills' },
  // Save › Projections (THL-197 GR-33, at /save/projections): this month,
  // the next 30 days and savings in a year, each as a range, and the growth
  // calculator (THL-135, at /save/calculator). The investing screens (GR-16,
  // GR-37, GR-10) live under it too.
  // Save › Learn (THL-134 GR-11, at /save/learn): five short modules before
  // investing, and two explainers. Open to everyone from day one.
  learn:         { label: 'Learn',
                   hint: 'Short reads on the basics of investing, at your pace' },
  projections:   { label: 'Projections',
                   hint: 'Where this month, the next 30 days and your savings are heading' },
  // Cash flow › Calendar (THL-245 CAL-01, THL-255, at /cash-flow/calendar):
  // the month day by day, what's due, and how past days went.
  calendar:      { label: 'Calendar',
                   hint: 'What’s coming up, and how the month has gone day by day' },
  review:        { label: 'Needs a look', short: 'Review',
                   hint: 'Everything Pearl isn’t sure about, with its best guess' },
  transactions:  { label: 'Transactions', short: 'Transactions',
                   hint: 'Search, filter and check every transaction' },
  // Profile (Pearl S-01): the hub, and the pages it opens. Each Profile page
  // draws a breadcrumb back to the hub instead of a sub-tab strip.
  profile:       { label: 'Profile',
                   hint: 'Your accounts, rules, sign-in and privacy' },
  // Profile › Accounts (THL-120, AM-01): linking a bank through Plaid,
  // signing in to one again and syncing live here since Connections went (C1).
  accounts:      { label: 'Accounts',
                   hint: 'Your accounts, how each one counts, and linking a bank' },
  // Profile › Categories and rules (S-03): the rules she saved.
  rules:         { label: 'Categories and rules',
                   hint: 'The rules Pearl sorts by, and what you leave out' },
  // Profile › Sign-in and security, with S-02 (change the sign-in email).
  security:      { label: 'Sign-in and security',
                   hint: 'Your email, passkeys and signing out' },
  // Profile › Income and bills (THL-45, THL-127): the pay and regular bills
  // she confirmed after linking, and the check run again. It replaced the
  // prototype "Income & commitments" page and its piggy banks. `short` is
  // what a phone shows where the full label will not fit.
  income:        { label: 'Income and bills', short: 'Income',
                   hint: 'What comes in, and the regular bills set aside' },
  // Profile › Notifications (THL-139 N-02): which nudges, and how.
  notifications: { label: 'Notifications',
                   hint: 'Payday, weekly check-in, progress and milestones' },
  // Profile › Privacy and consent (THL-117 CN-04, CN-05).
  consent:       { label: 'Privacy and consent',
                   hint: 'What you’ve agreed to, and how to change it' },
  // Profile › Your data (THL-116 D-01 to D-04): download a copy, or delete
  // the account.
  data:          { label: 'Your data',
                   hint: 'Download a copy or delete your account' },
  // Profile › How we protect you (THL-115 T-04, with T-02 and T-03).
  protect:       { label: 'How we protect you',
                   hint: 'What Pearl can and can’t do' },
  goals:         { label: 'Save',
                   hint: 'Your Anchor, your treasure chests and your saving goal' },
};

// The sidebar as the Pearl Handoff File draws it (2026-10-15): Home, Cash
// flow, Save and Wins, with Profile at the foot. A group holding one panel
// shows no sub-navigation; Cash flow's pages draw their own tabs
// (Transactions · Insights), as do Save's.
export const GROUPS = [
  // Home (THL-9, THL-44, THL-125): the page people open the app for, so it
  // is first and where the app lands. Budgets and Debts live with it
  // (THL-236).
  { key: 'home', label: 'Home', panels: ['home'],
    hint: 'What’s safe to spend this month',
    icon: 'M3 10.5 12 3l9 7.5M5 9v11h5v-6h4v6h5V9' },
  // Cash flow: the list (Pearl TX-01), what needs a look one tap away,
  // Insights as its second tab (GR-28), and Budgets and Debts (THL-209,
  // decided 2026-10-15).
  { key: 'cashflow', label: 'Cash flow', short: 'Cash flow',
    panels: ['transactions', 'calendar', 'review', 'insights', 'budgets', 'debts'],
    hint: 'Every transaction, the calendar, what needs a look, your month in pictures, budgets and debts',
    icon: 'M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0' },
  // Save (THL-240, THL-248): the Anchor and treasure chests, then what the
  // savings could grow into. Projections, the calculator and Learn are its
  // own pages, reached from it, not pills (`tabs: false`).
  { key: 'save', label: 'Save', panels: ['goals', 'projections', 'learn'], tabs: false,
    hint: 'Your Anchor, your treasure chests, and what they could grow into',
    // A lifebuoy, as NAV-01/NAV-02 draw it: a ring, the hole, four spokes.
    icon: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M14.8 9.2l3.6-3.6M5.6 18.4l3.6-3.6' },
  // Wins (THL-239): the milestone path and what's next.
  { key: 'wins', label: 'Wins', panels: ['path'],
    hint: 'Your path, and the one next step',
    // A starfish, as the design system's Icon/starfish draws it (THL-209):
    // five soft rounded arms with a dot on each, not a pointed star.
    icon: 'M10 4.5A2 2 0 0 1 14 4.5C14 6.9 13.67 7.65 14.88 8.54C16.09 9.42 16.71 8.87 18.99 8.13A2 2 0 0 1 20.23 11.93C17.94 12.67 17.12 12.59 16.66 14.01C16.2 15.44 16.91 15.85 18.32 17.8A2 2 0 0 1 15.08 20.15C13.67 18.21 13.5 17.4 12 17.4C10.5 17.4 10.33 18.21 8.92 20.15A2 2 0 0 1 5.68 17.8C7.09 15.85 7.8 15.44 7.34 14.01C6.88 12.59 6.06 12.67 3.77 11.93A2 2 0 0 1 5.01 8.13C7.29 8.87 7.91 9.42 9.12 8.54C10.33 7.65 10 6.9 10 4.5ZM12 6h.01M18.18 10.49h.01M15.82 17.76h.01M8.18 17.76h.01M5.82 10.49h.01' },
  // At the foot (THL-104, Pearl S-01): the Profile hub, and the pages it
  // opens — Accounts, Categories and rules, Sign-in and security, Income and
  // bills, Notifications and the three Privacy pages — each with
  // a breadcrumb back to it, so the group shows no sub-tab strip (`crumbs`).
  { key: 'profile', label: 'Profile',
    panels: ['profile', 'accounts', 'rules', 'security', 'income', 'notifications', 'consent',
             'data', 'protect'], foot: true, crumbs: true,
    hint: 'Your accounts, rules, sign-in and privacy',
    icon: 'M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z' },
];

// Keys that are no longer panels of their own but are still linked to from
// across the app and from the insights, which carry a tab name in their data.
// The Income and commitments page (`plan`) became Income and bills (THL-127);
// its piggy banks are Goals' treasure chests, so a link to them lands there.
// The Mortgage page is gone: its payments are read from your accounts now,
// and a mortgage payment is a regular bill.
// The old landing tab and the old Settings group still resolve, so any link
// or saved address that names them lands somewhere real. So do the pages
// removed in C1: Connections and From a file land on Accounts, where a bank is
// linked now; Trips on the list; Categories on Categories and rules (S-03).
// The old Sign-in page is Sign-in and security now. The prototype Insights
// page (`overview`) was replaced by Growth › Insights (THL-196 GR-28).
export const ALIASES = {
  plan: 'income', piggy: 'goals', mortgage: 'income', today: 'home', settings: 'profile',
  banks: 'accounts', import: 'accounts', categories: 'rules',
  account: 'security', signin: 'security', overview: 'insights',
  // The old Growth group (2026-10-15): its Path is on Wins, the rest on
  // Save and Cash flow; a link to the group lands on the path.
  growth: 'path',
};

// Where on that page the aliased thing actually is, when it isn't the top.
// Without this a link lands at the top of a long page with no sign of what it
// pointed at, which is indistinguishable from a button that did nothing.
export const ANCHORS = {};

/**
 * Turn a group key or a panel key into both.
 *
 * Panels link to each other by panel key and should not have to know about the
 * grouping, so this accepts either: 'settings' opens the group at its first
 * panel, 'income' opens the same group at that panel.
 */
export function resolve(key) {
  const target = ALIASES[key] ?? key;
  // A page wins over a group of the same name: `transactions` is the list
  // itself, which is also the page its group opens on.
  const owner = GROUPS.find((g) => g.panels.includes(target));
  if (owner) return [owner.key, target];
  const group = GROUPS.find((g) => g.key === target);
  if (group) return [group.key, group.panels[0]];
  return ['home', 'home'];
}
