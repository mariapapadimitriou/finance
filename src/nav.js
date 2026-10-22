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
                   hint: 'Your Allowance this month, and how we worked it out' },
  // Cash flow › Budgets (THL-168 B-01): every category, from her usual month.
  budgets:       { label: 'Budgets',
                   hint: 'A budget for every category, starting at your usual month' },

  // Cash flow › Insights (THL-186, THL-196 GR-28, at /cashflow/insights): the
  // month against her usual, in pictures, with a detail view behind each.
  insights:      { label: 'Insights',
                   hint: 'Your month against your usual, and where the money went' },
  // Cash flow › Debts (THL-49 D-02): every balance owed, from before Pearl too.
  debts:         { label: 'Debts',
                   hint: 'Everything you owe, and the minimums counted as bills' },


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

};

// The sidebar as the Pearl Handoff File draws it (2026-10-15): Home, Cash
// flow, Save and Wins, with Profile at the foot. A group holding one panel
// shows no sub-navigation; Cash flow's pages draw their own tabs
// (Transactions · Insights), as do Save's.
export const GROUPS = [
  // Home (2026-10-21, stripped down): where the app lands — the greeting,
  // what needs a look, and the way into Transactions. The old Home's
  // safe-to-spend, path, wins and cards went with Save and Wins.
  { key: 'home', label: 'Home', panels: ['home'],
    hint: 'What needs a look, and the way to your transactions',
    icon: 'M3 10.5 12 3l9 7.5M5 9v11h5v-6h4v6h5V9' },
  // Cash flow: the list (Pearl TX-01), what needs a look one tap away,
  // Insights as its second tab (GR-28), and Budgets and Debts (THL-209,
  // decided 2026-10-15).
  { key: 'cashflow', label: 'Cash flow', short: 'Cash flow',
    panels: ['transactions', 'calendar', 'review', 'insights', 'budgets', 'debts'],
    hint: 'Every transaction, the calendar, what needs a look, your month in pictures, budgets and debts',
    icon: 'M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 16c2-2 4-2 6 0s4 2 6 0 4-2 6 0' },
  // At the foot (THL-104, Pearl S-01): the Profile hub, and the pages it
  // opens — Accounts, Categories and rules, Sign-in and security, Income and
  // bills, Notifications and the three Privacy pages — each with
  // a breadcrumb back to it, so the group shows no sub-tab strip (`crumbs`).
  // Help and support (the sidebar's foot in the Pearl Handoff File): How we
  // protect you, with its two detail pages.
  { key: 'help', label: 'Help and support', panels: ['protect'], foot: true, crumbs: true,
    hint: 'What Pearl can and can’t do',
    icon: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01' },
  { key: 'profile', label: 'Profile',
    panels: ['profile', 'accounts', 'rules', 'security', 'income', 'notifications', 'consent',
             'data'], foot: true, crumbs: true,
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
  plan: 'income', piggy: 'home', mortgage: 'income', today: 'home', settings: 'profile',
  banks: 'accounts', import: 'accounts', categories: 'rules',
  account: 'security', signin: 'security', overview: 'insights',
  // Save, Wins and the old Growth group are gone (2026-10-21); a link to
  // any of their pages lands on Home.
  growth: 'home', path: 'home', goals: 'home', projections: 'home', learn: 'home',
  save: 'home', wins: 'home',
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
